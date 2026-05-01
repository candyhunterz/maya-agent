# Wire Protocol

Length-prefixed JSON frames over a named pipe (Linux: unix domain socket; Windows: named pipe via Qt; Windows dev fallback: TCP loopback).

See `docs/superpowers/specs/2026-05-01-maya-agent-v1-design.md` for design rationale.

## Frame format

Each frame is:

```
[ 4 bytes: big-endian unsigned int — body length ][ <body length> bytes: UTF-8 JSON ]
```

Implementations:
- Encoder: `maya_agent.core.frames.encode_frame(payload: dict) -> bytes`
- Decoder: `maya_agent.core.frames.FrameDecoder` — stateful, supports incremental
  feed across socket-chunk boundaries. Raises `FrameError` on oversize frames
  (default cap 16 MiB) or invalid JSON.

## Connection lifecycle

```
sidecar                           Maya panel
  │                                  │
  │  (TCP/pipe connect)              │
  │ ───────────────────────────────► │
  │                                  │
  │  AuthMessage{session_token}      │
  │ ───────────────────────────────► │
  │                                  │ ── verify with hmac.compare_digest
  │                                  │
  │  ToolInventoryMessage{tools}     │
  │ ◄─────────────────────────────── │ ── only sent after auth succeeds
  │                                  │
  │  ... normal traffic ...          │
```

Mismatched session tokens cause silent socket drop (no diagnostic frame). The
sidecar typically learns of failure when its next `receive()` returns nothing.

## Message types

Every message is a JSON object with a `type` discriminator field. Messages are
defined in `src/maya_agent/core/protocol.py` as pydantic models.

### Sidecar → Panel

| `type`            | Fields                                                    | When                                          |
|-------------------|-----------------------------------------------------------|-----------------------------------------------|
| `auth`            | `session_token: str`                                      | First frame after connect (mandatory)         |
| `tool_call`       | `intent_id`, `call_id`, `tool: str`, `args: dict`         | Agent decided to invoke a tool                |
| `thinking`        | `intent_id`, `text: str`                                  | Agent emitted private reasoning (logged only) |
| `assistant_message` | `intent_id`, `text: str`                                | Mid-intent narrator output                    |
| `clarify_question`| `intent_id`, `text: str`                                  | Agent needs user input                        |
| `intent_finished` | `intent_id`, `summary: str`, `user_message: str`          | Intent completed normally                     |
| `intent_failed`   | `intent_id`, `error: str`                                 | Intent crashed or LLM call failed             |

### Panel → Sidecar

| `type`              | Fields                                                       | When                                              |
|---------------------|--------------------------------------------------------------|---------------------------------------------------|
| `tool_inventory`    | `tools: list[dict]`                                          | First frame after auth handshake succeeds         |
| `user_intent`       | `intent_id`, `text: str`                                     | User pressed Send                                 |
| `clarify_response`  | `intent_id`, `text: str`                                     | User answered a `clarify_question`                |
| `cancel`            | `intent_id`                                                  | User pressed Stop                                 |
| `tool_result`       | `intent_id`, `call_id`, `ok: bool`, `value`, `error: str?`   | Panel finished dispatching a `tool_call`          |

## Tool inventory entries

Each tool in `tool_inventory.tools` is a dict with keys:

- `name: str` — snake_case identifier
- `description: str` — sent to the LLM as part of the system prompt
- `mutating: bool` — informs the LLM whether the tool changes scene state
- `json_schema: dict` — pydantic-generated JSON schema for the tool's args model

The sidecar performs a light schema check (required fields present, no extras)
before dispatching. The Maya-side dispatcher does full pydantic validation.

## Parsing

Use `parse_message(dict) -> Message` (a `TypeAdapter` over the discriminated
union). Use `encode_message(Message) -> dict` for the inverse. Both round-trip
cleanly through `encode_frame` / `FrameDecoder`.
