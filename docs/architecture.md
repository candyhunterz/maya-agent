# Architecture

See `docs/superpowers/specs/2026-05-01-maya-agent-v1-design.md` for the full design rationale.

## Process boundaries

Two processes:

1. **Sidecar (CPython, standalone).** Runs the agent loop. Talks HTTP to Ollama. Talks length-prefixed JSON over a named pipe (Linux: unix domain socket; Windows dev: TCP loopback fallback) to Maya. Imports nothing from `maya.cmds`.
2. **Maya process.** Runs the Qt panel, the `QLocalServer`, the tool dispatcher. Loads tool implementations (which lazy-import `maya.cmds`). Sends tool inventory to the sidecar at handshake. Receives tool calls and returns results.

## Module map

- `tools_common` — `Tool` ABC, `ToolArgs`, `ToolResult`. Pure schemas. No Maya import.
- `maya_agent.core` — Tool registry, plugin loader, wire protocol, frame codec.
- `maya_agent.sidecar` — Agent loop, LLM client, prompts, `MayaClient` (transport).
- `maya_agent.maya` — Qt panel, command server, tool dispatcher, bootstrap, example tools.

## Data flow

```
User types intent in panel
    │
    ▼
panel.send(UserIntentMessage) ──► CommandServer ──► sidecar (MayaClient.receive)
                                                          │
                                                          ▼
                                                  AgentLoop.run_intent
                                                          │
                       ┌──────────────────────────────────┼──────────────────────────────┐
                       ▼                                  ▼                              ▼
                 LLM (Ollama)                       ToolCallMessage                 IntentFinishedMessage
                       │                                  │                              │
                       ▼                                  ▼                              ▼
              raw JSON response          panel dispatcher.dispatch(tool, args)   panel renders user_message
                                                          │
                                                          ▼
                                          ToolResultMessage ──► sidecar (resolves call_id future)
```

## Auth handshake (v1-mandatory)

1. Panel generates a 32-byte URL-safe session token at startup, writes to `~/.maya-agent/session-<pid>.token` with `0600` perms.
2. Sidecar reads the token via `--session-token-file` (CLI) or `MAYA_AGENT_SESSION_TOKEN` (env).
3. Sidecar's first frame after connect MUST be `AuthMessage{session_token}`.
4. Server validates with `hmac.compare_digest`. On mismatch, the socket is dropped silently. On match, the server sends `ToolInventoryMessage` and starts emitting normal traffic.

## Outer per-intent undo chunk (v1-mandatory)

The panel opens `cmds.undoInfo(openChunk=True, chunkName=f"agent: {short_intent}")` when sending a `user_intent`, closes on `intent_finished` / `intent_failed`. Inner per-tool chunks (opened by the dispatcher for `mutating=True` tools) nest inside. Result: a single `Ctrl+Z` reverts the whole agentic action.
