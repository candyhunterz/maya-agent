# Maya Agent v1 — Design

**Date:** 2026-05-01
**Author:** Pipeline TD (drafted with Claude during brainstorming session)
**Status:** Approved for implementation planning

## Summary

A Maya-integrated agentic system that takes natural-language intent ("clean up Euler discontinuities on the arm controls") and executes it through a curated set of tools wrapping Maya operations. The agent runs in a sidecar Python process against a local Ollama server, communicating with Maya over a named pipe. Every mutating tool call is wrapped in a Maya undo chunk so a single Ctrl+Z reverts a tool atomically.

This document specifies the framework v1. The framework is studio-agnostic and eventually open-sourceable. Studio-specific tools live in a separate plugin repo loaded via environment variable.

## Goals

- Natural-language interface to Maya animation operations via a single-model agent
- Hard isolation between the LLM and Maya: the LLM never runs in Maya's interpreter, and Maya only executes pre-registered tool implementations
- Studio-agnostic framework + clean plugin contract so proprietary tools can be added without touching framework code
- Backend-agnostic LLM layer so model and inference server can be swapped without code changes
- Eval harness that runs in CI without Maya installed, using recorded LLM responses for determinism

## Non-Goals (v1)

- Scene-state checkpoints. Reverting relies on Maya's undo stack via `cmds.undoInfo` chunks per tool call.
- Confirmation gating for "dangerous" operations.
- Hot reload of plugins. Sidecar restart is cheap; Maya stays up.
- Token-level streaming inside a turn. One JSON object per turn is sufficient.
- Parallel tool calls. Schema enforces single-tool-per-turn.
- Multi-agent / planner-executor split. Single-model agent.
- RAG / vector knowledge base.
- Disk persistence of chat history or cross-intent memory.
- Stale-replacement of older observations (deferred — see Risks).
- Prompt caching (deferred until Gemma 4 at the studio).
- Live integration eval execution against `mayapy` (stub only).
- Authentication on the named pipe (relies on OS-level ACLs).
- Telemetry beyond stdlib `logging`.
- Multi-Maya-instance coordination (each Maya has its own pipe path including PID).

## Architectural Decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | Tool calls via Ollama `format=json_schema`, single tool per turn, ReAct loop | Portable across model families; avoids spotty native function-calling support; failure mode is mechanical "schema violation → retry" |
| 2 | `QLocalServer` over named pipe inside Maya, length-prefixed JSON, panel-as-server topology | One process boundary, full-duplex JSON, OS-managed access control, no firewall prompts |
| 3 | Plugin discovery via `MAYA_AGENT_PLUGIN_PATHS` env var, directory scan, optional `plugin.toml`, first-write-wins with WARNING | Matches how VFX studios already distribute Python code; no pip-install-into-Maya step |
| 4 | Best-interpretation + opt-in `clarify` (cap 3/intent), per-intent summaries as cross-intent memory (last 10), `action` discriminator schema with `thinking` field | Balances autonomy with safety on ambiguity; bounded memory prevents context explosion |
| 5 | Tool-call recorder + fixture observations as primary eval, `mayapy` integration eval as opt-in second tier; three-matcher sequence syntax with `allow_extra_calls` | Catches the failure mode that actually matters during prompt iteration (wrong tool, wrong order); avoids the tar pit of maintaining a stateful mock scene |
| 6 | No checkpoints — rely on Maya undo chunks per tool call | Maya's undo covers ~95% of what checkpoints would; tool authors mark file/shell ops as `mutating: bool` for log labeling |
| 7 | LLM backend abstracted behind `LLMClient` Protocol; `OllamaClient` is one implementation | Trivial abstraction (~6 lines), allows swap to vLLM / OpenAI-compatible / internal endpoint without agent-loop changes |
| 8 | Soft-cancel by default, opt-in fast-cancel via `cancel_token` parameter | Default is right for fast tools (most); long-running tools opt in; checkpoint absence makes "in-flight call finishes" safe enough |

## System Topology

```
┌────────────────────────────┐                    ┌─────────────────────────────────┐
│ Sidecar process (CPython)  │                    │ Maya process                    │
│                            │                    │                                 │
│  AgentLoop                 │                    │  Qt panel (chat, log, status)   │
│   ├─ LLMClient ────────► Ollama (HTTP)          │   │                            │
│   │   (or vLLM / other)    │                    │   ├─ QLocalServer (named pipe) │
│   │                        │                    │   │   accepts sidecar           │
│   ├─ MayaClient ◄──────────┼─── named pipe ────►│   │                            │
│   │   length-prefixed JSON │                    │   ├─ ToolRegistry              │
│   │                        │                    │   │   (plugin loader)          │
│   ├─ Tool inventory        │                    │   │                            │
│   │   (received at         │                    │   └─ ToolDispatcher            │
│   │    handshake)          │                    │       └─ undoInfo chunks       │
│   │                        │                    │            └─ tool.execute()    │
│   └─ IntentRunner          │                    │                                 │
│       (state machine per   │                    │  All maya.cmds run here only.   │
│        intent)             │                    │                                 │
└────────────────────────────┘                    └─────────────────────────────────┘
```

The sidecar has zero Maya knowledge. It receives the tool inventory at handshake time and works with it. The studio plugin repo is on `MAYA_AGENT_PLUGIN_PATHS` *only inside Maya*; the sidecar never imports plugin modules.

## Repo Structure

```
maya-agent/                          # framework repo, eventually open-sourceable
├── README.md
├── pyproject.toml                   # framework deps: httpx, pydantic, pyside6 (dev only)
├── .gitignore
│
├── src/
│   ├── maya_agent/
│   │   ├── __init__.py
│   │   ├── core/                    # framework primitives, no Maya import
│   │   │   ├── tool.py              # Tool base class, schema helpers
│   │   │   ├── registry.py          # ToolRegistry
│   │   │   ├── protocol.py          # JSON message shapes (pydantic models)
│   │   │   └── plugin_loader.py     # env var → directory scan
│   │   │
│   │   ├── sidecar/                 # runs in standalone CPython
│   │   │   ├── __main__.py          # entry: python -m maya_agent.sidecar
│   │   │   ├── agent_loop.py        # ReAct loop, intent runner, summaries
│   │   │   ├── llm_client.py        # LLMClient Protocol
│   │   │   ├── ollama_client.py     # httpx-based, format=json_schema
│   │   │   ├── recording_clients.py # RecordingLLMClient, ReplayLLMClient
│   │   │   ├── maya_client.py       # QLocalSocket client / asyncio raw socket
│   │   │   ├── prompts.py           # system prompt builder, tool inventory rendering
│   │   │   └── state.py             # cross-intent memory, summaries
│   │   │
│   │   └── maya/                    # imports maya.cmds — only loaded inside Maya
│   │       ├── command_server.py    # QLocalServer, panel-as-server
│   │       ├── tool_dispatcher.py   # undo chunks, args validation, signature inspection
│   │       ├── panel.py             # Qt dockable widget, chat + log + status
│   │       ├── maya_bootstrap.py    # userSetup hook, mod file installer
│   │       └── tools/               # framework-shipped example tools
│   │           ├── __init__.py
│   │           ├── inspect_scene.py
│   │           ├── query_animation_curves.py
│   │           ├── find_euler_discontinuities.py
│   │           ├── fix_euler_discontinuities.py
│   │           └── playblast.py
│   │
│   └── tools_common/                # shared between sidecar and Maya: schemas only
│       └── __init__.py              # NO maya.cmds. ToolArgs, ToolResult, Tool ABC.
│
├── tests/
│   ├── unit/                        # fast, no Maya, pure Python
│   │   ├── test_protocol.py
│   │   ├── test_registry.py
│   │   ├── test_plugin_loader.py
│   │   └── test_agent_loop_with_mocks.py
│   │
│   └── eval/                        # the (A) eval harness
│       ├── conftest.py              # mock dispatcher, fixture loader
│       ├── runner.py
│       ├── matchers.py              # the three sequence matchers
│       ├── recordings/              # LLM request/response pairs for replay mode
│       └── cases/
│           ├── euler_cleanup_basic.json
│           ├── euler_cleanup_ambiguous_arms.json
│           ├── playblast_with_assumptions.json
│           ├── tool_error_recovery.json
│           ├── unknown_tool_request.json
│           └── step_limit_exceeded.json
│
├── scripts/
│   ├── run_sidecar.py               # convenience launcher
│   ├── install_into_maya.py         # writes a .mod file pointing at this repo
│   └── run_integration_eval.py      # opt-in mayapy eval — stub for v1
│
└── docs/
    ├── architecture.md
    ├── writing-a-tool.md            # plugin author guide
    ├── protocol.md                  # message shapes reference
    └── superpowers/
        └── specs/
            └── 2026-05-01-maya-agent-v1-design.md   # this document
```

The studio plugin repo (created separately at work) has the shape:

```
studio-maya-agent-plugins/
├── plugin.toml                      # name, version, min_maya_version, deps
├── src/
│   ├── studio_rig_tools/
│   │   ├── __init__.py
│   │   └── ...
│   └── studio_anim_tools/
│       └── ...
└── tests/
```

Studio sets `MAYA_AGENT_PLUGIN_PATHS=C:\studio\maya-agent-plugins\src` and the framework loader walks it.

## Core Interfaces

### Tool

```python
# src/tools_common/tool.py
from typing import ClassVar
from pydantic import BaseModel

class ToolArgs(BaseModel):
    """Base for per-tool argument schemas. Subclass and add fields."""
    pass

class ToolResult(BaseModel):
    ok: bool
    value: object | None = None     # JSON-serializable result for the model
    error: str | None = None        # human-readable error if ok=False

class Tool:
    name: ClassVar[str]                       # unique snake_case identifier
    description: ClassVar[str]                # 1-3 sentences. Read by the LLM.
    args_model: ClassVar[type[ToolArgs]]      # pydantic model defining args
    mutating: ClassVar[bool] = False          # informs undo chunking + panel log

    def execute(
        self,
        args: ToolArgs,
        *,
        cancel_token: "CancelToken | None" = None,
    ) -> ToolResult: ...

    @classmethod
    def to_inventory_entry(cls) -> dict:
        return {
            "name": cls.name,
            "description": cls.description,
            "json_schema": cls.args_model.model_json_schema(),
            "mutating": cls.mutating,
        }
```

The dispatcher inspects `execute`'s signature (`inspect.signature`) to decide whether to thread the `cancel_token` through — tool authors who don't need fast cancel just omit the parameter.

**Lazy-import rule:** tool modules MUST NOT import `maya.cmds` at module top level. `from maya import cmds` happens inside `execute()`. This allows the eval harness and CI to load tool classes without a Maya install. Plugin loader includes a static AST check; modules that violate the rule are skipped with a warning.

### AgentLoop

```python
# src/maya_agent/sidecar/agent_loop.py

@dataclass
class IntentRequest:
    intent_id: str
    text: str

@dataclass
class IntentResult:
    intent_id: str
    summary: str         # ≤3 sentences, stored as cross-intent memory
    user_message: str    # rendered in the panel
    trace: list[dict]    # full ReAct trace for logging/eval
    terminal_action: str # "finish" | "step_limit" | "cancelled" | "failed"

class AgentLoop:
    def __init__(
        self,
        llm: LLMClient,
        maya: MayaClient,
        inventory: list[dict],            # from handshake
        model: str,                        # required, no default
        *,
        temperature: float = 0.0,
        max_steps: int = 20,
        max_clarifies: int = 3,
        summary_window: int = 10,
    ): ...

    async def run_intent(
        self,
        request: IntentRequest,
        *,
        on_event: Callable[[AgentEvent], None],
    ) -> IntentResult: ...
```

`on_event` streams progress to the panel mid-execution: `ThinkingEvent`, `ToolCallStartedEvent`, `ToolCallFinishedEvent`, `ClarifyQuestionEvent`, `AssistantMessageEvent`. The sidecar's `MayaClient` translates events into outbound socket messages.

### LLMClient

```python
# src/maya_agent/sidecar/llm_client.py
from typing import Protocol

class LLMClient(Protocol):
    async def generate_structured(
        self,
        messages: list[ChatMessage],
        json_schema: dict,
        *,
        model: str,
        temperature: float = 0.0,
        timeout_s: float = 120.0,
    ) -> dict:
        """Returns parsed JSON object conforming to json_schema. Raises on failure."""
```

V1 implementations:
- `OllamaClient` — talks to Ollama HTTP API, uses `format` parameter for schema enforcement
- `RecordingLLMClient(inner: LLMClient, recording_path: Path)` — wraps any client, writes (request, response) pairs to JSONL
- `ReplayLLMClient(recording_path: Path)` — reads JSONL, returns recorded responses by request hash; raises on cache miss

### Command Server Protocol

**Wire format:** length-prefixed JSON. Each frame is a 4-byte big-endian unsigned integer giving body length, followed by `length` bytes of UTF-8 JSON.

**Messages** (all carry `type` discriminator):

```python
# Maya/panel → sidecar
{"type": "tool_inventory", "tools": [<inventory entry>, ...]}     # handshake on connect
{"type": "user_intent",       "intent_id": str, "text": str}
{"type": "clarify_response",  "intent_id": str, "text": str}
{"type": "cancel",            "intent_id": str}
{"type": "tool_result",       "intent_id": str, "call_id": str,
                              "ok": bool, "value": Any|None, "error": str|None}

# Sidecar → Maya/panel
{"type": "tool_call",          "intent_id": str, "call_id": str,
                               "tool": str, "args": object}
{"type": "thinking",           "intent_id": str, "text": str}
{"type": "assistant_message",  "intent_id": str, "text": str}
{"type": "clarify_question",   "intent_id": str, "text": str}
{"type": "intent_finished",    "intent_id": str, "summary": str, "user_message": str}
{"type": "intent_failed",      "intent_id": str, "error": str}
```

**Connection lifecycle:**

1. Maya boots, panel starts `QLocalServer` on `\\.\pipe\maya-agent-<pid>` (or `/tmp/maya-agent-<pid>.sock` on Linux). Pipe path shown in panel UI.
2. Sidecar started (manually via terminal or via panel "Start agent" button).
3. Sidecar connects.
4. Maya immediately sends `tool_inventory`. Sidecar builds prompts and response JSON schema from this inventory.
5. Panel can send `user_intent`.
6. Connection drop → both sides clean up; in-flight intent abandoned; panel offers reconnect.

## Plugin System

`MAYA_AGENT_PLUGIN_PATHS` is `os.pathsep`-separated. Order in the env var determines override precedence: paths listed earlier shadow later ones. Framework example tools are appended internally, so studio plugins always shadow examples by default.

**Per-path scan:**

1. If `plugin.toml` exists in the path root, parse it. Pydantic-validate. Required fields: `name`, `version`. Optional: `description`, `min_maya_version`, `max_maya_version`, `requires_tools`. If Maya version doesn't match, log warning and skip the directory entirely.
2. Walk all `.py` files (recursively, following packages). Import via `importlib.util.spec_from_file_location` to avoid polluting `sys.path`.
3. AST-check each module before import: reject if `maya.cmds` (or `from maya import cmds` etc.) appears at module level.
4. After import, find `Tool` subclasses. Validate each: `name` set + non-empty + snake_case; `description` set + non-empty; `args_model` is a `ToolArgs` subclass; `execute` is defined; `args_model.model_json_schema()` doesn't raise.
5. Register into `ToolRegistry`. **First-write-wins.** Duplicate `name` → log `WARNING: Tool 'foo' from <path A> shadows tool 'foo' from <path B>`, skip the second.
6. After all paths walked, log summary: `Loaded 14 tools from 3 plugin paths (2 shadowed, 1 import error)`.

**Failure handling:** fail-soft. Plugin import errors are logged, the panel shows a warning banner with a "click to expand" tracebacks list and a "Retry" button. The agent runs without those tools. A `--strict` flag (CLI / install verification) makes plugin errors fatal.

## Agent Loop Behavior

### Output schema

```python
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "thinking":     {"type": "string", "description": "Private reasoning. The user does not see this."},
        "action":       {"type": "string", "enum": ["tool_call", "clarify", "finish"]},
        "tool":         {"type": ["string", "null"]},
        "arguments":    {"type": ["object", "null"]},
        "question":     {"type": ["string", "null"]},
        "user_message": {"type": ["string", "null"]},
        "summary":      {"type": ["string", "null"]},
    },
    "required": ["thinking", "action"],
    "additionalProperties": False,
}
```

Permissive shape; Python-side validation enforces field combinations per `action`. `oneOf`-discriminated unions are inconsistently supported across grammar engines, so we keep the schema flat.

### System prompt structure

```
You are a Maya animation assistant working inside the user's Maya session.
You accomplish tasks by calling tools. You never write or generate Maya code directly —
you only choose tools from the inventory below.

## Response format
Every response is one JSON object:
- thinking: short private reasoning, the user does not see this
- action: "tool_call" | "clarify" | "finish"

For action="tool_call":
  tool: string (name from inventory)
  arguments: object matching that tool's argument schema

For action="clarify":
  question: the question to ask the user

For action="finish":
  user_message: what the user sees as your reply
  summary: ≤3 sentences capturing what was done

## Decision policy
- Prefer to act on the most likely interpretation; explain assumptions in your final user_message.
- Use clarify only when guessing wrong would mutate the scene in a way expensive to revert.
- You may clarify at most {max_clarifies} times per intent.
- After a tool returns an error, read it carefully before retrying — most errors are wrong arguments, not missing capability.

## Tool inventory
{compact rendering of each tool's name, description, args, mutating flag}

## Memory of previous intents
{rendered list of (user_text, summary) pairs from the last N intents, oldest first}

## Current intent
{the user's text}
```

The system prompt is rebuilt fresh per intent. This loses prompt-caching but gains hot tool-inventory updates and clean memory accounting. When the studio enables prompt caching with Gemma 4, the system prompt will be made stable per session and only updated when the inventory changes.

### Within-intent message history

```
system:    <prompt>
user:      <intent text>
assistant: <model's first JSON output verbatim>
user:      [tool_result: find_euler_discontinuities]
           {"ok": true, "value": {...}}
assistant: <next JSON>
user:      [user_clarification]
           the L_arm_FK_CTL, not the IK one
...
```

Bracketed prefixes (`[tool_result: <name>]`, `[user_clarification]`, `[step_limit_warning]`, `[parse_error]`) are discipline markers. Cheap, grep-able, help the model orient.

### Error feedback patterns

| Failure | Observation injected as next user turn |
|---|---|
| `action=tool_call` but no `tool` field | `[parse_error] action was tool_call but 'tool' was missing. Retry.` |
| Tool name not in inventory | `[tool_result: <name>] {"ok": false, "error": "Unknown tool. Available: <list>"}` |
| Args fail pydantic validation | `[tool_result: <name>] {"ok": false, "error": "Invalid arguments: <pydantic message>"}` |
| Tool raises during execute | `[tool_result: <name>] {"ok": false, "error": "<exception class>: <message>"}` (no traceback to model; full traceback to panel debug log) |
| LLM HTTP error / timeout | Retry once with 2s backoff. Second failure → `intent_failed`. |
| Maya socket disconnects | `intent_failed` immediately; panel reconnects. |

All recoverable failures count toward `max_steps`.

### Circuit breaker

`max_steps=20` is hard, soft-handled. At step `max_steps - 1`, inject `[step_limit_warning] One step remaining. Use action=finish.` If still tool_call/clarify at step `max_steps`, force-finish with auto-generated `user_message: "Step limit reached before completion. Trace summary: <last 3 tool calls + outcomes>"` and `summary: "Hit step limit on intent: <user text>"`.

### Cancel semantics

Soft-cancel by default: sidecar marks intent cancelled, stops issuing new tool calls, discards the result of any in-flight call when it returns. Maya still finishes the in-flight call. Maya's undo + re-inspect on next intent covers state drift.

Tools opt in to fast-cancel by declaring a `cancel_token` parameter in `execute`. Dispatcher inspects the signature, threads a token through if present. Tool can check `cancel_token.is_set()` at safe points (between frames in playblast, between curves in batch ops).

### Summary generation

Two parallel records per intent:
- **Narrative summary** — the model's `finish.summary` field. Stored as text. Used as cross-intent memory in future prompts.
- **Factual trace metadata** — `(tool_name, ok, args_summary)` tuples extracted from the loop. Used by the panel's "previous intents" view and the eval harness. Never feeds back into prompts.

### Observation context (deferred decision)

Observations live verbatim in the conversation history for the rest of the intent. For Gemma 3 27B with 128K context and `max_steps=20`, this is fine. We instrument total prompt-token count per intent; when p95 crosses 50% of context window, we add stale-replacement: older observations of the same tool replaced with `[older <tool> observation; superseded]`, most recent wins.

## Qt Panel

**Single dockable panel** via `cmds.workspaceControl`. Vertical stack:

- Status row: connection state (gray/yellow/green/red dot), model name, plugin failure banner if any
- Chat area: user/agent messages interleaved, with **inline collapsible tool entries** showing tool name, status icon (⟳/✓/✗), and on expand: arguments + result preview. Errors expand by default.
- Multi-line text input + buttons: Send (Ctrl+Enter), Undo last, Clear chat, Stop (visible only mid-intent)

Tool log entries are inline in the chat, not a separate pane or tab.

Optional thinking-toggle in a ⚙ menu — off by default. When on, renders the model's `thinking` field as a faded inline block above each tool entry.

**Threading:**
- Socket I/O runs on a `QThread` owning the `QLocalSocket`
- Inbound frames delivered to main thread via `Signal(dict)` (Qt queued connection)
- Main-thread slot dispatches by `type`:
  - `tool_call` → wrap in `cmds.undoInfo(openChunk=True, chunkName=tool)`, run `tool.execute()`, `closeChunk`, send `tool_result`
  - Other event types → update chat model, panel renders
- Outbound: main thread enqueues onto a `queue.Queue` the I/O thread drains

`maya.cmds` is main-thread-only; the dispatcher is already on the main thread (Qt queued signal delivery), so we don't need `executeInMainThreadWithResult`. Tool calls block the Maya UI for their duration; this is documented in `writing-a-tool.md`.

**Sidecar lifecycle:** both manual launch and panel-button auto-launch supported. Default is manual (developer workflow benefits from sidecar logs in a real terminal). Panel "Start agent" button does `subprocess.Popen` and pipes logs to `~/.maya-agent/logs/sidecar-<timestamp>.log`.

**Persistence:** chat history in-memory only for v1. Cleared on Maya restart. "Clear chat" button resets manually. Cross-intent memory clears with chat.

## Eval Harness

### Case file shape (tests/eval/cases/*.json)

```json
{
  "name": "euler_cleanup_basic",
  "description": "User requests Euler cleanup on FK arm controls.",
  "intent": "clean up Euler discontinuities on the L_arm FK controls",
  "clarify_responses": [],
  "fixture_observations": [
    {"match_tool": "inspect_scene",
     "response": {"ok": true, "value": {...}}},
    {"match_tool": "find_euler_discontinuities",
     "match_args_contain": {"objects": ["rig:L_arm_FK_CTL"]},
     "response": {"ok": true, "value": {"discontinuities": [...]}}},
    {"match_tool": "fix_euler_discontinuities",
     "response": {"ok": true, "value": {"fixed_count": 1}}}
  ],
  "expected_calls": [
    "inspect_scene",
    {"tool": "find_euler_discontinuities", "args_contain": {"objects": ["rig:L_arm_FK_CTL"]}},
    "fix_euler_discontinuities"
  ],
  "allow_extra_calls": true,
  "terminal_action": "finish",
  "max_steps": 10
}
```

**Fixture matching:** first matching `(match_tool, optional match_args_contain)` wins. No match → observation is `{"ok": false, "error": "no fixture defined for this call"}`.

**Sequence matchers** (`expected_calls` items):
- Bare string: tool name, exact match in this position
- `{"tool": str, "args_contain": dict}`: positional + partial arg match
- `{"any_order": [str, ...]}`: all listed tools must appear (positionally located in the sequence as a block); order within the block doesn't matter

`allow_extra_calls=True` means the agent can call additional tools beyond those listed; `expected_calls` only asserts presence + relative order.

### LLM modes

`MAYA_AGENT_EVAL_MODE` env var: `live` | `record` | `replay`. Default: replay if recording exists, else live.

- `live` — real LLM, real Ollama. Slow, network-dependent, mildly stochastic.
- `record` — `live` + write `(messages, schema, model) → response` pairs to `tests/eval/recordings/<case_name>.jsonl`. Used to refresh recordings after a deliberate prompt change.
- `replay` — read recordings only, no Ollama. Deterministic, ~50ms per case. CI uses this.

CI fails if any case has no recording (prevents accidental skip).

### Initial cases (v1)

1. `euler_cleanup_basic` — happy-path multi-tool sequence
2. `euler_cleanup_ambiguous_arms` — exercises the clarify path
3. `playblast_with_assumptions` — agent picks defaults and explains them
4. `tool_error_recovery` — fixture returns `ok: false`, agent retries with corrected args
5. `unknown_tool_request` — user asks for capability we don't have, agent finishes gracefully
6. `step_limit_exceeded` — fixture loop forces > max_steps, asserts circuit-breaker behavior

### Integration eval (deferred)

`scripts/run_integration_eval.py` is a stub for v1. Future shape: same case files, `mayapy`-spawned headless Maya, fixture `.ma` scene per case, real tool execution against the scene. Wired up at the studio when bringing the framework in.

## Risks & Documented Concerns

1. **Gemma 3 27B determinism:** even at `temperature=0`, Ollama's sampler is not bit-exact deterministic across runs. Record/replay handles eval determinism; users see slight variance in production. Acceptable for v1.
2. **Ollama JSON schema enforcement varies by version.** Pin Ollama ≥ 0.4.x (or whichever version has stable `format` schema support at ship time). Document in README.
3. **Main-thread blocking during tool execution.** Inherent to `cmds`; documented in `writing-a-tool.md`. Long tools should call `cmds.refresh()` periodically and use `cmds.progressBar`.
4. **Plugin import errors compound.** Studio plugin repos accumulate; warning banner can become permanent. Mitigation: surface failed plugins with one-click traceback access, and add `--strict` mode for CI/install verification.
5. **Cancel-semantics drift.** Soft-cancel + opt-in fast-cancel is two contracts. Tool authors might not realize they can opt in. Mitigation: docs page + a `make_cancellable_tool` decorator if it becomes a pain point in v2.
6. **No state divergence detection.** If the user manually edits the scene during an intent, the agent's prior observations are stale. v1 doesn't detect this. v2 candidate: scene state digest in `tool_result`.
7. **Observation context growth.** Single-tool-per-turn loops can run 10-20 calls. Each observation lives verbatim in context. Mitigation if needed: stale-replacement (deferred).

## Success Criteria for v1

- All six eval cases pass in `replay` mode in CI
- Manual end-to-end smoke succeeds: open Maya 2024+, start panel from menu, click "Start agent", type *"find euler discontinuities on the selected control"* on a small test scene with a known discontinuity, observe correct tool sequence (`inspect_scene` → `find_euler_discontinuities` → `finish`) and correct result rendering in the chat
- Plugin loading works against an externally-located test plugin (a tiny throwaway repo on disk) referenced by `MAYA_AGENT_PLUGIN_PATHS`
- Sidecar can be killed mid-intent and the panel recovers gracefully (status goes red, in-flight intent fails, reconnect works)
- Repo is open-sourceable: no studio-internal references, dependencies are all permissively-licensed, README explains setup in a way someone outside your studio could follow

## Open Questions / Future Work

- **Stale-replacement of older observations** — add when p95 prompt tokens cross 50% of model context window
- **Hot reload of plugins** — defer; restart sidecar covers it
- **Disk persistence of chat / cross-intent memory** — add when users ask
- **Live integration eval** — build at the studio against a real `.ma` fixture
- **Streaming responses** — add when prompt iteration stabilizes; Ollama supports streaming structured output
- **Multi-tool parallelism** — would require schema changes; no current need
- **Prompt caching** — add when stable on Gemma 4 at the studio; expected meaningful latency win
- **Scene state digest** — for state divergence detection if it becomes an issue
- **MCP server wrapping** — could expose the tool inventory as an MCP server later, for non-Maya agents to drive Maya. Out of v1 but a clean future extension given the architecture.
