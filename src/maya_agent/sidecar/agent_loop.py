"""AgentLoop: ReAct-style state machine, single intent at a time.

Calls LLMClient with the response schema; parses the action; dispatches
tool_call to the MayaClient mock or real; injects observations back into the
message history; handles clarify, errors, and the step-limit circuit breaker.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from maya_agent.sidecar.llm_client import ChatMessage, LLMClient
from maya_agent.sidecar.prompts import build_system_prompt, RESPONSE_SCHEMA
from maya_agent.sidecar.state import CrossIntentMemory

_log = logging.getLogger(__name__)


@dataclass
class IntentRequest:
    intent_id: str
    text: str


@dataclass
class IntentResult:
    intent_id: str
    summary: str
    user_message: str
    trace: list[dict]
    terminal_action: str  # "finish" | "step_limit" | "cancelled" | "failed"


class AgentLoop:
    def __init__(
        self,
        llm: LLMClient,
        maya: Any,                      # has call_tool() and emit(); MayaClient or mock
        inventory: list[dict],
        model: str,
        *,
        temperature: float = 0.0,
        max_steps: int = 20,
        max_clarifies: int = 3,
        memory: CrossIntentMemory | None = None,
    ) -> None:
        self._llm = llm
        self._maya = maya
        self._inventory = inventory
        self._inventory_by_name = {t["name"]: t for t in inventory}
        self._model = model
        self._temperature = temperature
        self._max_steps = max_steps
        self._max_clarifies = max_clarifies
        self._memory = memory or CrossIntentMemory()
        self._clarify_queues: dict[str, asyncio.Queue[str]] = {}
        self._cancelled: set[str] = set()

    async def provide_clarify_response(self, intent_id: str, text: str) -> None:
        if intent_id in self._clarify_queues:
            await self._clarify_queues[intent_id].put(text)

    def cancel(self, intent_id: str) -> None:
        self._cancelled.add(intent_id)

    async def run_intent(
        self,
        request: IntentRequest,
        *,
        on_event: Callable[[dict], None],
    ) -> IntentResult:
        intent_id = request.intent_id
        self._clarify_queues[intent_id] = asyncio.Queue()
        clarify_count = 0
        trace: list[dict] = []

        system_prompt = build_system_prompt(
            self._inventory,
            max_clarifies=self._max_clarifies,
            summaries=self._memory.as_list(),
            current_intent=request.text,
        )
        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=request.text),
        ]

        try:
            for step in range(self._max_steps):
                if intent_id in self._cancelled:
                    return self._build_result(
                        intent_id, "Cancelled by user.", "Cancelled.", trace, "cancelled"
                    )

                if step == self._max_steps - 1:
                    messages.append(ChatMessage(
                        role="user",
                        content="[step_limit_warning] One step remaining. Use action=finish.",
                    ))

                try:
                    raw = await self._llm.generate_structured(
                        messages, RESPONSE_SCHEMA, model=self._model,
                        temperature=self._temperature,
                    )
                except Exception as e:
                    _log.exception("LLM call failed")
                    return self._build_result(
                        intent_id, f"LLM error: {e}", f"LLM error: {e}", trace, "failed"
                    )

                # Append the model's raw output as the assistant turn
                messages.append(ChatMessage(role="assistant", content=json.dumps(raw)))
                trace.append({"step": step, "raw": raw})

                thinking = raw.get("thinking", "") or ""
                # Defense in depth: truncate runaway thinking even though the schema
                # enforces maxLength. Engines that don't honor maxLength shouldn't
                # be able to starve our context with self-talk.
                from maya_agent.sidecar.prompts import THINKING_HARD_CAP_CHARS
                if len(thinking) > THINKING_HARD_CAP_CHARS:
                    _log.warning("thinking field exceeded hard cap (%d chars); truncating",
                                 len(thinking))
                    thinking = thinking[:THINKING_HARD_CAP_CHARS] + "...[truncated]"
                    raw["thinking"] = thinking  # so the trace records the truncated version
                if thinking:
                    on_event({"type": "thinking", "intent_id": intent_id, "text": thinking})

                action = raw.get("action")
                if action == "finish":
                    summary = raw.get("summary") or ""
                    user_message = raw.get("user_message") or ""
                    self._memory.add(request.text, summary)
                    on_event({"type": "intent_finished", "intent_id": intent_id,
                              "summary": summary, "user_message": user_message})
                    return self._build_result(intent_id, summary, user_message, trace, "finish")

                if action == "clarify":
                    if clarify_count >= self._max_clarifies:
                        messages.append(ChatMessage(
                            role="user",
                            content="[parse_error] You have used all clarifies. Pick the best interpretation and act.",
                        ))
                        continue
                    clarify_count += 1
                    question = raw.get("question") or ""
                    on_event({"type": "clarify_question", "intent_id": intent_id, "text": question})
                    answer = await self._clarify_queues[intent_id].get()
                    messages.append(ChatMessage(
                        role="user", content=f"[user_clarification]\n{answer}",
                    ))
                    continue

                if action == "tool_call":
                    obs = await self._dispatch_tool_call(intent_id, raw, on_event)
                    messages.append(ChatMessage(role="user", content=obs))
                    continue

                # Unknown action
                messages.append(ChatMessage(
                    role="user",
                    content=f"[parse_error] Unknown action {action!r}. Use tool_call, clarify, or finish.",
                ))

            # Step limit hit and not finished — force-finish
            forced_summary = f"Hit step limit on intent: {request.text}"
            forced_msg = "Step limit reached before completion."
            self._memory.add(request.text, forced_summary)
            return self._build_result(intent_id, forced_summary, forced_msg, trace, "step_limit")
        finally:
            self._clarify_queues.pop(intent_id, None)
            self._cancelled.discard(intent_id)

    async def _dispatch_tool_call(self, intent_id: str, raw: dict,
                                   on_event: Callable[[dict], None]) -> str:
        tool_name = raw.get("tool")
        args = raw.get("arguments") or {}
        if not tool_name:
            return "[parse_error] action was tool_call but 'tool' was missing. Retry."
        if tool_name not in self._inventory_by_name:
            available = ", ".join(self._inventory_by_name)
            return (f"[tool_result: {tool_name}] "
                    f'{{"ok": false, "error": "Unknown tool. Available: {available}"}}')
        # Validate args by reconstructing a model-like check via JSON schema
        # (For simplicity we trust pydantic-shaped schemas; full validation happens in Maya.)
        # Sidecar-side validation: check required fields and unknown fields.
        schema = self._inventory_by_name[tool_name]["json_schema"]
        err = _light_validate(schema, args)
        if err is not None:
            return f'[tool_result: {tool_name}] {{"ok": false, "error": "Invalid arguments: {err}"}}'

        call_id = str(uuid.uuid4())
        on_event({"type": "tool_call", "intent_id": intent_id, "call_id": call_id,
                  "tool": tool_name, "args": args})
        try:
            result = await self._maya.call_tool(intent_id, call_id, tool_name, args)
        except Exception as e:
            return (f'[tool_result: {tool_name}] '
                    f'{{"ok": false, "error": "Dispatch failed: {type(e).__name__}: {e}"}}')
        on_event({"type": "tool_result", "intent_id": intent_id, "call_id": call_id,
                  "ok": result.get("ok", False), "value": result.get("value"),
                  "error": result.get("error")})
        return f"[tool_result: {tool_name}]\n{json.dumps(result)}"

    def _build_result(self, intent_id, summary, user_message, trace, terminal):
        return IntentResult(
            intent_id=intent_id, summary=summary, user_message=user_message,
            trace=trace, terminal_action=terminal,
        )


def _light_validate(schema: dict, args: dict) -> str | None:
    """Minimal JSON-schema check: required fields present, no extras allowed.
    Real validation happens Maya-side; this catches obvious agent mistakes early."""
    if not isinstance(args, dict):
        return f"arguments must be an object, got {type(args).__name__}"
    required = set(schema.get("required") or [])
    missing = required - set(args)
    if missing:
        return f"missing required fields: {sorted(missing)}"
    props = set((schema.get("properties") or {}).keys())
    if props:  # only enforce if schema declares properties
        extras = set(args) - props
        if extras:
            return f"unknown fields: {sorted(extras)}"
    return None
