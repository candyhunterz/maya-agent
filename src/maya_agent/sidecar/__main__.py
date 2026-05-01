"""Sidecar process entry point.

Usage:
  python -m maya_agent.sidecar \
      --pipe /tmp/maya-agent-12345.sock \
      --session-token-file ~/.maya-agent/session-12345.token \
      --model gemma3:27b

Reads --pipe, --model, --session-token(/-file), --ollama-base-url, --max-steps
from argv. Each has a corresponding env var fallback (MAYA_AGENT_*).

Connects to the named pipe / TCP loopback, sends an auth message with the
session token, awaits the tool_inventory message (server only sends after
successful auth), then services user_intent / clarify_response / cancel
messages by running the AgentLoop.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from maya_agent.core.protocol import (
    AuthMessage, UserIntentMessage, ClarifyResponseMessage, CancelMessage,
    ToolInventoryMessage, ToolCallMessage, ToolResultMessage, ThinkingMessage,
    AssistantMessage, ClarifyQuestionMessage, IntentFinishedMessage, IntentFailedMessage,
    parse_message,
)
from maya_agent.sidecar.agent_loop import AgentLoop, IntentRequest
from maya_agent.sidecar.maya_client import MayaClient
from maya_agent.sidecar.ollama_client import OllamaClient


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="maya-agent-sidecar")
    p.add_argument("--pipe", default=os.environ.get("MAYA_AGENT_PIPE"),
                   help="Named pipe / unix socket path the Maya panel is listening on. "
                        "On Windows dev, may be 'host:port' for TCP loopback.")
    p.add_argument("--model", default=os.environ.get("MAYA_AGENT_MODEL"),
                   help="LLM model identifier (e.g., gemma3:27b)")
    p.add_argument("--ollama-base-url", default=os.environ.get(
        "MAYA_AGENT_OLLAMA_URL", "http://localhost:11434"))
    p.add_argument("--session-token", default=os.environ.get("MAYA_AGENT_SESSION_TOKEN"),
                   help="Session token expected by the Maya panel (literal value).")
    p.add_argument("--session-token-file", default=os.environ.get("MAYA_AGENT_SESSION_TOKEN_FILE"),
                   help="Path to a file containing the session token. Read at startup.")
    p.add_argument("--max-steps", type=int, default=20)
    p.add_argument("--log-file", default=None)
    args = p.parse_args()
    if not args.pipe:
        p.error("--pipe is required (or set MAYA_AGENT_PIPE)")
    if not args.model:
        p.error("--model is required (or set MAYA_AGENT_MODEL)")
    if not args.session_token and not args.session_token_file:
        p.error("--session-token or --session-token-file is required "
                "(or set MAYA_AGENT_SESSION_TOKEN / MAYA_AGENT_SESSION_TOKEN_FILE)")
    return args


def _load_session_token(args: argparse.Namespace) -> str:
    if args.session_token:
        return args.session_token.strip()
    return Path(args.session_token_file).read_text(encoding="utf-8").strip()


def _setup_logging(log_file: str | None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


class _MayaTransport:
    """Adapter exposing call_tool/emit on top of MayaClient for AgentLoop."""
    def __init__(self, client: MayaClient) -> None:
        self.client = client
        self._pending: dict[str, asyncio.Future] = {}

    async def call_tool(self, intent_id: str, call_id: str, tool: str, args: dict) -> dict:
        await self.client.send(ToolCallMessage(
            intent_id=intent_id, call_id=call_id, tool=tool, args=args,
        ))
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._pending[call_id] = fut
        try:
            return await fut
        finally:
            self._pending.pop(call_id, None)

    def deliver_tool_result(self, msg: ToolResultMessage) -> None:
        fut = self._pending.get(msg.call_id)
        if fut and not fut.done():
            fut.set_result({"ok": msg.ok, "value": msg.value, "error": msg.error})

    async def emit(self, event: dict) -> None:
        intent_id = event.get("intent_id", "")
        t = event.get("type")
        if t == "thinking":
            await self.client.send(ThinkingMessage(intent_id=intent_id, text=event["text"]))
        elif t == "intent_finished":
            await self.client.send(IntentFinishedMessage(
                intent_id=intent_id, summary=event["summary"], user_message=event["user_message"]))
        elif t == "clarify_question":
            await self.client.send(ClarifyQuestionMessage(intent_id=intent_id, text=event["text"]))
        # tool_call/tool_result events are emitted as part of the dispatcher round-trip,
        # not via on_event — those flow through call_tool().


async def _main() -> int:
    args = _parse_args()
    _setup_logging(args.log_file)
    log = logging.getLogger("sidecar")

    session_token = _load_session_token(args)
    log.info("Connecting to %s", args.pipe)
    client = MayaClient()

    if sys.platform == "win32":
        # On Windows, asyncio doesn't natively support named-pipe client connect.
        # Dev-machine workaround: accept "host:port" form and use TCP loopback.
        # Linux production uses connect_pipe() against the unix domain socket
        # (asyncio.open_unix_connection — fully supported, no workaround).
        if ":" in args.pipe:
            host, port = args.pipe.rsplit(":", 1)
            await client.connect_tcp(host, int(port))
        else:
            log.error("Windows named-pipe connect not implemented in v1; use host:port form")
            return 2
    else:
        await client.connect_pipe(args.pipe)

    # Auth handshake: send our session token first, before anything else.
    # Server validates with constant-time compare; on mismatch it closes the
    # connection silently and we fail at the next receive().
    await client.send(AuthMessage(session_token=session_token))

    msg = await client.receive()
    if not isinstance(msg, ToolInventoryMessage):
        log.error("First message after auth was not tool_inventory: %s "
                  "(connection likely rejected by server — bad token?)",
                  type(msg).__name__)
        return 3
    inventory = msg.tools
    log.info("Auth accepted; received inventory: %d tools", len(inventory))

    transport = _MayaTransport(client)
    llm = OllamaClient(base_url=args.ollama_base_url)
    agent = AgentLoop(
        llm=llm, maya=transport, inventory=inventory, model=args.model,
        max_steps=args.max_steps,
    )

    active_tasks: dict[str, asyncio.Task] = {}

    async def handle_intent(req: IntentRequest):
        try:
            async def event_handler(event: dict) -> None:
                await transport.emit(event)
            result = await agent.run_intent(req, on_event=lambda e: asyncio.create_task(transport.emit(e)))
            if result.terminal_action == "failed":
                await client.send(IntentFailedMessage(intent_id=req.intent_id, error=result.summary))
            elif result.terminal_action != "finish":
                # cancelled or step_limit — already emitted finished/cancelled-style; but ensure final state
                pass
        except Exception as e:
            log.exception("Intent crashed")
            await client.send(IntentFailedMessage(intent_id=req.intent_id, error=str(e)))

    while True:
        msg = await client.receive()
        if isinstance(msg, UserIntentMessage):
            req = IntentRequest(intent_id=msg.intent_id, text=msg.text)
            active_tasks[msg.intent_id] = asyncio.create_task(handle_intent(req))
        elif isinstance(msg, ClarifyResponseMessage):
            await agent.provide_clarify_response(msg.intent_id, msg.text)
        elif isinstance(msg, CancelMessage):
            agent.cancel(msg.intent_id)
        elif isinstance(msg, ToolResultMessage):
            transport.deliver_tool_result(msg)
        else:
            log.warning("Unhandled message type: %s", type(msg).__name__)


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(_main()) or 0)
    except KeyboardInterrupt:
        sys.exit(0)
