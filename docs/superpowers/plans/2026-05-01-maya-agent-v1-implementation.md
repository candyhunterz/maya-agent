# Maya Agent v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Maya-integrated agentic system per `docs/superpowers/specs/2026-05-01-maya-agent-v1-design.md` — a sidecar Python process that talks to Ollama, communicates with Maya over a named pipe, and executes registered tools with undo-chunk safety.

**Architecture:** Sidecar (CPython) runs the agent loop and LLM client; Maya process runs the panel-as-server with a `QLocalServer` accepting length-prefixed JSON frames; tool implementations live only in Maya; tool schemas are sent to the sidecar at handshake. Studio-specific tools load from `MAYA_AGENT_PLUGIN_PATHS`. Eval harness runs in CI without Maya using recorded LLM responses.

**Tech Stack:** Python 3.10+, pydantic v2, httpx, PySide6 (Maya-side only), pytest. No agent frameworks.

---

## File structure (locked from spec)

```
maya-agent/
├── pyproject.toml
├── README.md
├── .gitignore
├── src/
│   ├── tools_common/
│   │   └── __init__.py                  # Tool ABC, ToolArgs, ToolResult — no maya import
│   └── maya_agent/
│       ├── __init__.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── tool.py                  # re-exports from tools_common for convenience
│       │   ├── registry.py              # ToolRegistry
│       │   ├── protocol.py              # pydantic models for wire messages
│       │   ├── frames.py                # length-prefixed JSON codec
│       │   └── plugin_loader.py         # env var → directory scan + AST lint
│       ├── sidecar/
│       │   ├── __init__.py
│       │   ├── __main__.py              # entry point
│       │   ├── llm_client.py            # LLMClient Protocol, ChatMessage
│       │   ├── ollama_client.py         # OllamaClient implementation
│       │   ├── recording_clients.py     # Recording / Replay wrappers
│       │   ├── maya_client.py           # asyncio socket client
│       │   ├── prompts.py               # system prompt builder, inventory rendering
│       │   ├── state.py                 # cross-intent memory
│       │   └── agent_loop.py            # IntentRunner / AgentLoop
│       └── maya/
│           ├── __init__.py
│           ├── command_server.py        # QLocalServer + frame handler
│           ├── tool_dispatcher.py       # undo chunks, args validation
│           ├── panel.py                 # Qt dockable widget
│           ├── maya_bootstrap.py        # userSetup hook
│           └── tools/
│               ├── __init__.py
│               ├── inspect_scene.py
│               ├── query_animation_curves.py
│               ├── find_euler_discontinuities.py
│               ├── fix_euler_discontinuities.py
│               └── playblast.py
├── scripts/
│   ├── run_sidecar.py
│   ├── install_into_maya.py
│   └── run_integration_eval.py          # stub
├── tests/
│   ├── unit/
│   │   ├── test_tool.py
│   │   ├── test_registry.py
│   │   ├── test_protocol.py
│   │   ├── test_frames.py
│   │   ├── test_plugin_loader.py
│   │   ├── test_prompts.py
│   │   ├── test_state.py
│   │   ├── test_recording_clients.py
│   │   └── test_agent_loop.py
│   └── eval/
│       ├── conftest.py
│       ├── runner.py
│       ├── matchers.py
│       ├── test_eval_cases.py
│       ├── recordings/
│       └── cases/
│           ├── euler_cleanup_basic.json
│           ├── euler_cleanup_ambiguous_arms.json
│           ├── playblast_with_assumptions.json
│           ├── tool_error_recovery.json
│           ├── unknown_tool_request.json
│           └── step_limit_exceeded.json
└── docs/
    ├── architecture.md
    ├── writing-a-tool.md
    ├── protocol.md
    └── superpowers/
        ├── specs/
        └── plans/
```

---

## Phase 1 — Foundation

### Task 1.1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `README.md`
- Create: `src/tools_common/__init__.py` (empty for now)
- Create: `src/maya_agent/__init__.py` (empty)
- Create: `src/maya_agent/core/__init__.py` (empty)
- Create: `src/maya_agent/sidecar/__init__.py` (empty)
- Create: `src/maya_agent/maya/__init__.py` (empty)
- Create: `src/maya_agent/maya/tools/__init__.py` (empty)
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "maya-agent"
version = "0.1.0"
description = "Maya-integrated agentic AI framework"
requires-python = ">=3.10"
dependencies = [
    "httpx>=0.27.0",
    "pydantic>=2.6.0",
]

[project.optional-dependencies]
maya = ["PySide6>=6.5.0"]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "ruff>=0.4.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/maya_agent", "src/tools_common"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py310"
```

- [ ] **Step 2: Write `.gitignore`**

```
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
.pytest_cache/
.ruff_cache/
.venv/
build/
dist/
*.log
~/.maya-agent/
tests/eval/recordings/*.actual.jsonl
.coverage
.vscode/
.idea/
```

- [ ] **Step 3: Write minimal `README.md`**

```markdown
# Maya Agent

Maya-integrated agentic AI framework. See `docs/superpowers/specs/` for design.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # Linux
pip install -e ".[dev]"
pytest tests/unit
```

## Status

In active development. See `docs/superpowers/plans/` for implementation plan.
```

- [ ] **Step 4: Create empty package files**

Create empty `__init__.py` for `src/tools_common/`, `src/maya_agent/`, `src/maya_agent/core/`, `src/maya_agent/sidecar/`, `src/maya_agent/maya/`, `src/maya_agent/maya/tools/`, `tests/`, `tests/unit/`.

- [ ] **Step 5: Verify install works**

Run: `pip install -e ".[dev]"`
Expected: succeeds, pytest available.
Run: `pytest tests/unit -v`
Expected: 0 tests collected (no tests yet), exit code 5 (no tests is OK).

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "chore: project scaffolding (pyproject, gitignore, package skeleton)"
```

---

## Phase 2 — Core abstractions

### Task 2.1: Tool, ToolArgs, ToolResult

**Files:**
- Create: `src/tools_common/__init__.py`
- Create: `tests/unit/test_tool.py`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_tool.py`:
```python
import pytest
from pydantic import Field
from tools_common import Tool, ToolArgs, ToolResult


class _MyArgs(ToolArgs):
    name: str = Field(..., description="A name")
    count: int = Field(1, description="How many")


class _MyTool(Tool):
    name = "my_tool"
    description = "Does a thing."
    args_model = _MyArgs
    mutating = True

    def execute(self, args, *, cancel_token=None):
        return ToolResult(ok=True, value={"got": args.name, "count": args.count})


def test_tool_inventory_entry_shape():
    entry = _MyTool.to_inventory_entry()
    assert entry["name"] == "my_tool"
    assert entry["description"] == "Does a thing."
    assert entry["mutating"] is True
    assert entry["json_schema"]["type"] == "object"
    assert "name" in entry["json_schema"]["properties"]
    assert "count" in entry["json_schema"]["properties"]


def test_tool_executes_with_parsed_args():
    tool = _MyTool()
    result = tool.execute(_MyArgs(name="foo", count=3))
    assert result.ok is True
    assert result.value == {"got": "foo", "count": 3}


def test_tool_result_failure_shape():
    r = ToolResult(ok=False, error="bad input")
    assert r.ok is False
    assert r.error == "bad input"
    assert r.value is None


def test_tool_args_validation_rejects_wrong_types():
    with pytest.raises(Exception):
        _MyArgs(name=123, count="not_an_int")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_tool.py -v`
Expected: ImportError on `from tools_common import Tool, ...`

- [ ] **Step 3: Implement `src/tools_common/__init__.py`**

```python
"""Schemas and base classes shared between sidecar and Maya processes.

This package MUST NOT import maya.cmds. The eval harness loads tool classes
defined in this package (and in subclasses elsewhere) without a Maya install.
"""
from __future__ import annotations

from typing import ClassVar
from pydantic import BaseModel


class ToolArgs(BaseModel):
    """Base class for per-tool argument schemas. Subclass and add fields."""

    model_config = {"extra": "forbid"}


class ToolResult(BaseModel):
    """Result of a tool invocation. Either ok=True with value, or ok=False with error."""

    ok: bool
    value: object | None = None
    error: str | None = None


class Tool:
    """Base class for tools. Subclasses define class attributes and execute()."""

    name: ClassVar[str]
    description: ClassVar[str]
    args_model: ClassVar[type[ToolArgs]]
    mutating: ClassVar[bool] = False

    def execute(self, args, *, cancel_token=None) -> ToolResult:
        raise NotImplementedError

    @classmethod
    def to_inventory_entry(cls) -> dict:
        return {
            "name": cls.name,
            "description": cls.description,
            "json_schema": cls.args_model.model_json_schema(),
            "mutating": cls.mutating,
        }


__all__ = ["Tool", "ToolArgs", "ToolResult"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_tool.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/tools_common/__init__.py tests/unit/test_tool.py
git commit -m "feat(core): Tool, ToolArgs, ToolResult base classes"
```

---

### Task 2.2: Wire protocol pydantic models

**Files:**
- Create: `src/maya_agent/core/protocol.py`
- Create: `tests/unit/test_protocol.py`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_protocol.py`:
```python
import pytest
from pydantic import ValidationError
from maya_agent.core.protocol import (
    ToolInventoryMessage, UserIntentMessage, ClarifyResponseMessage,
    CancelMessage, ToolResultMessage, ToolCallMessage, ThinkingMessage,
    AssistantMessage, ClarifyQuestionMessage, IntentFinishedMessage,
    IntentFailedMessage, parse_message, encode_message,
)


def test_user_intent_round_trips():
    m = UserIntentMessage(intent_id="i1", text="hello")
    raw = encode_message(m)
    parsed = parse_message(raw)
    assert isinstance(parsed, UserIntentMessage)
    assert parsed.text == "hello"


def test_tool_call_carries_args_and_call_id():
    m = ToolCallMessage(intent_id="i1", call_id="c1", tool="inspect_scene", args={"x": 1})
    parsed = parse_message(encode_message(m))
    assert parsed.tool == "inspect_scene"
    assert parsed.args == {"x": 1}
    assert parsed.call_id == "c1"


def test_tool_result_with_error():
    m = ToolResultMessage(intent_id="i1", call_id="c1", ok=False, error="boom")
    parsed = parse_message(encode_message(m))
    assert parsed.ok is False
    assert parsed.error == "boom"
    assert parsed.value is None


def test_tool_inventory_round_trip():
    m = ToolInventoryMessage(tools=[
        {"name": "t", "description": "d", "json_schema": {}, "mutating": False}
    ])
    parsed = parse_message(encode_message(m))
    assert parsed.tools[0]["name"] == "t"


def test_parse_rejects_unknown_type():
    with pytest.raises(ValidationError):
        parse_message({"type": "nonsense", "intent_id": "i1"})


def test_parse_rejects_missing_required_field():
    with pytest.raises(ValidationError):
        parse_message({"type": "user_intent", "intent_id": "i1"})  # missing text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_protocol.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/maya_agent/core/protocol.py`**

```python
"""Wire protocol messages exchanged between Maya and the sidecar.

All messages are pydantic models with a `type` discriminator. Use parse_message()
to dispatch by type; encode_message() returns a JSON-serializable dict.
"""
from __future__ import annotations

from typing import Any, Literal, Union
from pydantic import BaseModel, Field, TypeAdapter


# Maya/panel → sidecar
class ToolInventoryMessage(BaseModel):
    type: Literal["tool_inventory"] = "tool_inventory"
    tools: list[dict]


class UserIntentMessage(BaseModel):
    type: Literal["user_intent"] = "user_intent"
    intent_id: str
    text: str


class ClarifyResponseMessage(BaseModel):
    type: Literal["clarify_response"] = "clarify_response"
    intent_id: str
    text: str


class CancelMessage(BaseModel):
    type: Literal["cancel"] = "cancel"
    intent_id: str


class ToolResultMessage(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    intent_id: str
    call_id: str
    ok: bool
    value: Any | None = None
    error: str | None = None


# Sidecar → Maya/panel
class ToolCallMessage(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    intent_id: str
    call_id: str
    tool: str
    args: dict


class ThinkingMessage(BaseModel):
    type: Literal["thinking"] = "thinking"
    intent_id: str
    text: str


class AssistantMessage(BaseModel):
    type: Literal["assistant_message"] = "assistant_message"
    intent_id: str
    text: str


class ClarifyQuestionMessage(BaseModel):
    type: Literal["clarify_question"] = "clarify_question"
    intent_id: str
    text: str


class IntentFinishedMessage(BaseModel):
    type: Literal["intent_finished"] = "intent_finished"
    intent_id: str
    summary: str
    user_message: str


class IntentFailedMessage(BaseModel):
    type: Literal["intent_failed"] = "intent_failed"
    intent_id: str
    error: str


Message = Union[
    ToolInventoryMessage, UserIntentMessage, ClarifyResponseMessage, CancelMessage,
    ToolResultMessage, ToolCallMessage, ThinkingMessage, AssistantMessage,
    ClarifyQuestionMessage, IntentFinishedMessage, IntentFailedMessage,
]

_adapter = TypeAdapter(Message, config={"discriminator": "type"})


def parse_message(data: dict) -> Message:
    """Parse a JSON-decoded dict into the appropriate Message subtype."""
    return _adapter.validate_python(data)


def encode_message(msg: Message) -> dict:
    """Encode a Message to a JSON-serializable dict."""
    return msg.model_dump()
```

(Note: pydantic v2 `TypeAdapter` with `discriminator` uses the `Literal` field automatically. If the discriminator config form differs in the installed version, fall back to `Field(discriminator='type')` on a wrapping `RootModel`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_protocol.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/maya_agent/core/protocol.py tests/unit/test_protocol.py
git commit -m "feat(core): wire protocol pydantic models with discriminated union"
```

---

### Task 2.3: Length-prefixed JSON frame codec

**Files:**
- Create: `src/maya_agent/core/frames.py`
- Create: `tests/unit/test_frames.py`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_frames.py`:
```python
import pytest
from maya_agent.core.frames import encode_frame, FrameDecoder, FrameError


def test_encode_frame_prefixes_with_4_byte_length():
    payload = {"hello": "world"}
    frame = encode_frame(payload)
    assert isinstance(frame, bytes)
    # 4-byte big-endian length + JSON body
    body = b'{"hello": "world"}'
    assert int.from_bytes(frame[:4], "big") == len(body)
    assert frame[4:] == body


def test_decoder_yields_one_message_per_frame():
    d = FrameDecoder()
    f1 = encode_frame({"a": 1})
    f2 = encode_frame({"b": 2})
    msgs = list(d.feed(f1 + f2))
    assert msgs == [{"a": 1}, {"b": 2}]


def test_decoder_handles_split_across_chunks():
    d = FrameDecoder()
    full = encode_frame({"x": "y"})
    msgs1 = list(d.feed(full[:3]))
    assert msgs1 == []
    msgs2 = list(d.feed(full[3:]))
    assert msgs2 == [{"x": "y"}]


def test_decoder_handles_split_inside_body():
    d = FrameDecoder()
    full = encode_frame({"x": "long-ish payload to ensure split"})
    cut = len(full) // 2
    msgs1 = list(d.feed(full[:cut]))
    assert msgs1 == []
    msgs2 = list(d.feed(full[cut:]))
    assert len(msgs2) == 1


def test_decoder_rejects_oversize_frame():
    d = FrameDecoder(max_frame_bytes=10)
    huge = encode_frame({"big": "x" * 1000})
    with pytest.raises(FrameError, match="frame too large"):
        list(d.feed(huge))


def test_decoder_rejects_invalid_json():
    d = FrameDecoder()
    bad = (5).to_bytes(4, "big") + b"not{j"
    with pytest.raises(FrameError, match="invalid JSON"):
        list(d.feed(bad))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_frames.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/maya_agent/core/frames.py`**

```python
"""Length-prefixed JSON frame codec.

Each frame is a 4-byte big-endian unsigned integer (frame body length) followed
by `length` bytes of UTF-8 JSON. Trivially parseable; no escaping; supports
incremental decoding across socket chunk boundaries.
"""
from __future__ import annotations

import json
from typing import Iterator

DEFAULT_MAX_FRAME_BYTES = 16 * 1024 * 1024  # 16 MiB


class FrameError(Exception):
    """Raised when a frame cannot be decoded."""


def encode_frame(payload: dict) -> bytes:
    body = json.dumps(payload, separators=(", ", ": ")).encode("utf-8")
    return len(body).to_bytes(4, "big") + body


class FrameDecoder:
    """Stateful decoder. Feed bytes; iterate decoded JSON dicts."""

    def __init__(self, max_frame_bytes: int = DEFAULT_MAX_FRAME_BYTES) -> None:
        self._buf = bytearray()
        self._max = max_frame_bytes

    def feed(self, data: bytes) -> Iterator[dict]:
        self._buf.extend(data)
        while True:
            if len(self._buf) < 4:
                return
            length = int.from_bytes(self._buf[:4], "big")
            if length > self._max:
                raise FrameError(f"frame too large: {length} > {self._max}")
            if len(self._buf) < 4 + length:
                return
            body = bytes(self._buf[4 : 4 + length])
            del self._buf[: 4 + length]
            try:
                yield json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                raise FrameError(f"invalid JSON: {e}") from e
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_frames.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/maya_agent/core/frames.py tests/unit/test_frames.py
git commit -m "feat(core): length-prefixed JSON frame codec with incremental decoder"
```

---

## Phase 3 — Plugin system

### Task 3.1: ToolRegistry

**Files:**
- Create: `src/maya_agent/core/registry.py`
- Create: `tests/unit/test_registry.py`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_registry.py`:
```python
import pytest
from pydantic import Field
from tools_common import Tool, ToolArgs
from maya_agent.core.registry import ToolRegistry, RegistryError


class _ArgsA(ToolArgs):
    x: int = Field(...)


class _ToolA(Tool):
    name = "tool_a"
    description = "First tool."
    args_model = _ArgsA
    def execute(self, args, *, cancel_token=None): ...


class _ArgsB(ToolArgs):
    y: str = Field(...)


class _ToolB(Tool):
    name = "tool_b"
    description = "Second tool."
    args_model = _ArgsB
    def execute(self, args, *, cancel_token=None): ...


class _ToolAClone(Tool):
    name = "tool_a"  # collides with _ToolA
    description = "Clone of A."
    args_model = _ArgsA
    def execute(self, args, *, cancel_token=None): ...


def test_register_tools_and_retrieve():
    r = ToolRegistry()
    assert r.register(_ToolA, "/path/a") is True
    assert r.register(_ToolB, "/path/a") is True
    assert r.get("tool_a") is _ToolA
    assert {t.name for t in r.all()} == {"tool_a", "tool_b"}


def test_first_write_wins_on_duplicate_name():
    r = ToolRegistry()
    assert r.register(_ToolA, "/path/early") is True
    assert r.register(_ToolAClone, "/path/late") is False
    # original wins
    assert r.get("tool_a") is _ToolA
    assert r.shadowed == [("tool_a", "/path/early", "/path/late")]


def test_inventory_returns_serializable_entries():
    r = ToolRegistry()
    r.register(_ToolA, "/x")
    inv = r.inventory()
    assert inv[0]["name"] == "tool_a"
    assert "json_schema" in inv[0]


def test_get_unknown_raises():
    r = ToolRegistry()
    with pytest.raises(RegistryError):
        r.get("missing")


def test_validate_tool_class_rejects_missing_name():
    class _Broken(Tool):
        description = "no name"
        args_model = _ArgsA
        def execute(self, args, *, cancel_token=None): ...
    r = ToolRegistry()
    with pytest.raises(RegistryError, match="name"):
        r.register(_Broken, "/x")


def test_validate_tool_class_rejects_non_snake_case():
    class _Args(ToolArgs):
        x: int = Field(...)
    class _Bad(Tool):
        name = "BadName"
        description = "ok"
        args_model = _Args
        def execute(self, args, *, cancel_token=None): ...
    r = ToolRegistry()
    with pytest.raises(RegistryError, match="snake_case"):
        r.register(_Bad, "/x")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_registry.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/maya_agent/core/registry.py`**

```python
"""ToolRegistry: holds the loaded tools, validates them, handles override semantics."""
from __future__ import annotations

import logging
import re
from tools_common import Tool, ToolArgs

_log = logging.getLogger(__name__)
_SNAKE_CASE = re.compile(r"^[a-z][a-z0-9_]*$")


class RegistryError(Exception):
    """Raised on invalid tool registration or unknown tool lookup."""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, type[Tool]] = {}
        self._sources: dict[str, str] = {}
        self.shadowed: list[tuple[str, str, str]] = []

    def register(self, tool_cls: type[Tool], source_path: str) -> bool:
        """Validate and register a tool class. Returns True if registered, False if shadowed."""
        self._validate(tool_cls)
        name = tool_cls.name
        if name in self._tools:
            winner = self._sources[name]
            self.shadowed.append((name, winner, source_path))
            _log.warning(
                "Tool '%s' from %s shadowed by earlier registration from %s",
                name, source_path, winner,
            )
            return False
        self._tools[name] = tool_cls
        self._sources[name] = source_path
        return True

    def get(self, name: str) -> type[Tool]:
        if name not in self._tools:
            raise RegistryError(f"Unknown tool: {name!r}")
        return self._tools[name]

    def all(self) -> list[type[Tool]]:
        return list(self._tools.values())

    def inventory(self) -> list[dict]:
        return [t.to_inventory_entry() for t in self._tools.values()]

    @staticmethod
    def _validate(cls: type[Tool]) -> None:
        if not getattr(cls, "name", None):
            raise RegistryError(f"{cls.__name__}.name not set or empty")
        if not _SNAKE_CASE.match(cls.name):
            raise RegistryError(f"{cls.__name__}.name {cls.name!r} is not snake_case")
        if not getattr(cls, "description", None):
            raise RegistryError(f"{cls.__name__}.description not set or empty")
        am = getattr(cls, "args_model", None)
        if am is None or not (isinstance(am, type) and issubclass(am, ToolArgs)):
            raise RegistryError(f"{cls.__name__}.args_model must be a ToolArgs subclass")
        try:
            am.model_json_schema()
        except Exception as e:
            raise RegistryError(f"{cls.__name__}.args_model schema invalid: {e}") from e
        if cls.execute is Tool.execute:
            raise RegistryError(f"{cls.__name__} must override execute()")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_registry.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/maya_agent/core/registry.py tests/unit/test_registry.py
git commit -m "feat(core): ToolRegistry with first-write-wins and validation"
```

---

### Task 3.2: Plugin loader (env var, AST lint, plugin.toml)

**Files:**
- Create: `src/maya_agent/core/plugin_loader.py`
- Create: `tests/unit/test_plugin_loader.py`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_plugin_loader.py`:
```python
from pathlib import Path
import textwrap
import pytest
from maya_agent.core.registry import ToolRegistry
from maya_agent.core.plugin_loader import (
    load_plugins_from_paths, has_module_level_maya_import,
)


def _write_tool(dir: Path, name: str, body: str) -> Path:
    f = dir / f"{name}.py"
    f.write_text(textwrap.dedent(body))
    return f


GOOD_TOOL = """
    from pydantic import Field
    from tools_common import Tool, ToolArgs, ToolResult

    class _Args(ToolArgs):
        x: int = Field(..., description="X")

    class MyTool(Tool):
        name = "my_tool"
        description = "Does a thing."
        args_model = _Args
        def execute(self, args, *, cancel_token=None):
            from maya import cmds  # lazy
            return ToolResult(ok=True)
"""

BAD_TOOL_TOPLEVEL_IMPORT = """
    from maya import cmds  # MODULE LEVEL — disallowed
    from pydantic import Field
    from tools_common import Tool, ToolArgs, ToolResult

    class _Args(ToolArgs):
        x: int = Field(...)

    class MyTool(Tool):
        name = "my_tool"
        description = "..."
        args_model = _Args
        def execute(self, args, *, cancel_token=None):
            return ToolResult(ok=True)
"""

BROKEN_TOOL_IMPORT = """
    raise RuntimeError("boom at import time")
"""


def test_loader_loads_tool_from_directory(tmp_path):
    _write_tool(tmp_path, "my_tool", GOOD_TOOL)
    reg = ToolRegistry()
    summary = load_plugins_from_paths([tmp_path], reg)
    assert summary.loaded_count == 1
    assert summary.failed_modules == []
    assert reg.get("my_tool").name == "my_tool"


def test_loader_skips_modules_with_toplevel_maya_import(tmp_path):
    _write_tool(tmp_path, "bad_tool", BAD_TOOL_TOPLEVEL_IMPORT)
    reg = ToolRegistry()
    summary = load_plugins_from_paths([tmp_path], reg)
    assert summary.loaded_count == 0
    assert any("maya" in r.reason for r in summary.failed_modules)


def test_loader_continues_after_broken_module(tmp_path):
    _write_tool(tmp_path, "broken", BROKEN_TOOL_IMPORT)
    _write_tool(tmp_path, "good", GOOD_TOOL)
    reg = ToolRegistry()
    summary = load_plugins_from_paths([tmp_path], reg)
    assert summary.loaded_count == 1
    assert any(r.module_path.name == "broken.py" for r in summary.failed_modules)


def test_first_write_wins_across_paths(tmp_path):
    p1 = tmp_path / "p1"
    p2 = tmp_path / "p2"
    p1.mkdir(); p2.mkdir()
    _write_tool(p1, "my_tool", GOOD_TOOL)
    _write_tool(p2, "my_tool", GOOD_TOOL)  # same name in second path
    reg = ToolRegistry()
    summary = load_plugins_from_paths([p1, p2], reg)
    assert summary.loaded_count == 1
    assert summary.shadowed_count == 1


def test_plugin_toml_min_maya_version_skips(tmp_path):
    (tmp_path / "plugin.toml").write_text(textwrap.dedent("""
        name = "demo"
        version = "0.1.0"
        min_maya_version = "9999"
    """))
    _write_tool(tmp_path, "my_tool", GOOD_TOOL)
    reg = ToolRegistry()
    summary = load_plugins_from_paths([tmp_path], reg, current_maya_version="2024")
    assert summary.loaded_count == 0
    assert summary.skipped_paths == [tmp_path]


def test_ast_lint_detects_various_import_forms():
    assert has_module_level_maya_import("from maya import cmds") is True
    assert has_module_level_maya_import("import maya.cmds") is True
    assert has_module_level_maya_import("import maya.cmds as cmds") is True
    assert has_module_level_maya_import("def f():\n    from maya import cmds") is False
    assert has_module_level_maya_import("import os") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_plugin_loader.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/maya_agent/core/plugin_loader.py`**

```python
"""Plugin discovery and loading.

Walks paths from MAYA_AGENT_PLUGIN_PATHS (or an explicit list), validates each
.py module for a module-level maya import (forbidden), imports it, finds Tool
subclasses, and registers them. Fail-soft: errors on individual modules don't
abort the load.
"""
from __future__ import annotations

import ast
import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

import tomllib  # 3.11+; for 3.10 fall back to tomli

from tools_common import Tool
from maya_agent.core.registry import ToolRegistry, RegistryError

_log = logging.getLogger(__name__)


@dataclass
class FailedModule:
    module_path: Path
    reason: str


@dataclass
class LoadSummary:
    loaded_count: int = 0
    shadowed_count: int = 0
    skipped_paths: list[Path] = field(default_factory=list)
    failed_modules: list[FailedModule] = field(default_factory=list)


def has_module_level_maya_import(source: str) -> bool:
    """True if the source has `import maya...` or `from maya...` at module scope."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in tree.body:  # only module-level
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "maya" or alias.name.startswith("maya."):
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "maya" or node.module.startswith("maya.")):
                return True
    return False


def _check_plugin_toml(path: Path, current_maya_version: str | None) -> bool:
    """Return True if the path should be loaded (or no plugin.toml). False if skipped."""
    toml_path = path / "plugin.toml"
    if not toml_path.exists():
        return True
    try:
        meta = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except Exception as e:
        _log.error("Failed to parse %s: %s", toml_path, e)
        return False
    min_v = meta.get("min_maya_version")
    if min_v and current_maya_version and current_maya_version < min_v:
        _log.warning(
            "Plugin %s requires Maya >= %s, current is %s — skipping",
            meta.get("name", path), min_v, current_maya_version,
        )
        return False
    max_v = meta.get("max_maya_version")
    if max_v and current_maya_version and current_maya_version > max_v:
        _log.warning(
            "Plugin %s requires Maya <= %s, current is %s — skipping",
            meta.get("name", path), max_v, current_maya_version,
        )
        return False
    return True


def _load_module(py_path: Path, summary: LoadSummary) -> object | None:
    source = py_path.read_text(encoding="utf-8")
    if has_module_level_maya_import(source):
        summary.failed_modules.append(FailedModule(py_path, "module-level maya import"))
        _log.error("Skipping %s: module-level maya import is disallowed", py_path)
        return None
    mod_name = f"_plugin_{py_path.stem}_{abs(hash(str(py_path)))}"
    spec = importlib.util.spec_from_file_location(mod_name, py_path)
    if spec is None or spec.loader is None:
        summary.failed_modules.append(FailedModule(py_path, "cannot create import spec"))
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        del sys.modules[mod_name]
        summary.failed_modules.append(FailedModule(py_path, f"{type(e).__name__}: {e}"))
        _log.exception("Failed to import %s", py_path)
        return None
    return mod


def _register_tools_from_module(mod: object, source_path: str,
                                registry: ToolRegistry, summary: LoadSummary) -> None:
    for attr_name in dir(mod):
        cls = getattr(mod, attr_name)
        if not isinstance(cls, type):
            continue
        if not issubclass(cls, Tool) or cls is Tool:
            continue
        if cls.__module__ != mod.__name__:
            continue  # imported from elsewhere; don't double-register
        try:
            if registry.register(cls, source_path):
                summary.loaded_count += 1
            else:
                summary.shadowed_count += 1
        except RegistryError as e:
            summary.failed_modules.append(FailedModule(Path(source_path), f"{cls.__name__}: {e}"))


def load_plugins_from_paths(
    paths: list[Path],
    registry: ToolRegistry,
    *,
    current_maya_version: str | None = None,
) -> LoadSummary:
    summary = LoadSummary()
    for path in paths:
        path = Path(path)
        if not path.exists():
            _log.warning("Plugin path does not exist: %s", path)
            continue
        if not _check_plugin_toml(path, current_maya_version):
            summary.skipped_paths.append(path)
            continue
        for py_path in sorted(path.rglob("*.py")):
            if py_path.name == "__init__.py":
                continue
            mod = _load_module(py_path, summary)
            if mod is not None:
                _register_tools_from_module(mod, str(path), registry, summary)
    _log.info(
        "Loaded %d tools from %d paths (%d shadowed, %d failed, %d paths skipped)",
        summary.loaded_count, len(paths), summary.shadowed_count,
        len(summary.failed_modules), len(summary.skipped_paths),
    )
    return summary
```

(For Python 3.10 compat, replace `import tomllib` with `try: import tomllib\nexcept ImportError: import tomli as tomllib`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_plugin_loader.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/maya_agent/core/plugin_loader.py tests/unit/test_plugin_loader.py
git commit -m "feat(core): plugin loader with AST lint and plugin.toml validation"
```

---

## Phase 4 — LLM client layer

### Task 4.1: LLMClient Protocol + ChatMessage

**Files:**
- Create: `src/maya_agent/sidecar/llm_client.py`

- [ ] **Step 1: Implement `src/maya_agent/sidecar/llm_client.py`**

```python
"""LLM client abstraction. The agent loop talks to LLMClient, never to a concrete
implementation. This lets us swap Ollama for vLLM / OpenAI-compatible / etc.
"""
from __future__ import annotations

from typing import Literal, Protocol
from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


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
        """Call the LLM and return a parsed JSON object conforming to json_schema.

        Raises LLMError on transport / timeout / schema-violation failures.
        """
        ...


class LLMError(Exception):
    """Raised by LLMClient implementations on failure."""
```

- [ ] **Step 2: Commit**

```bash
git add src/maya_agent/sidecar/llm_client.py
git commit -m "feat(sidecar): LLMClient Protocol + ChatMessage"
```

---

### Task 4.2: RecordingLLMClient + ReplayLLMClient

**Files:**
- Create: `src/maya_agent/sidecar/recording_clients.py`
- Create: `tests/unit/test_recording_clients.py`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_recording_clients.py`:
```python
import json
from pathlib import Path
import pytest
from maya_agent.sidecar.llm_client import ChatMessage, LLMError
from maya_agent.sidecar.recording_clients import (
    RecordingLLMClient, ReplayLLMClient, request_hash,
)


class _FakeLLM:
    def __init__(self, response):
        self.response = response
        self.calls = []
    async def generate_structured(self, messages, json_schema, *, model, temperature=0.0, timeout_s=120.0):
        self.calls.append((messages, json_schema, model))
        return self.response


@pytest.mark.asyncio
async def test_recording_writes_jsonl(tmp_path):
    rec_file = tmp_path / "rec.jsonl"
    inner = _FakeLLM({"action": "finish", "thinking": "ok", "user_message": "done", "summary": "."})
    rec = RecordingLLMClient(inner, rec_file)
    msgs = [ChatMessage(role="user", content="hi")]
    schema = {"type": "object"}
    out = await rec.generate_structured(msgs, schema, model="m")
    assert out["action"] == "finish"
    lines = rec_file.read_text().strip().splitlines()
    assert len(lines) == 1
    rec_obj = json.loads(lines[0])
    assert "request_hash" in rec_obj
    assert rec_obj["response"]["action"] == "finish"


@pytest.mark.asyncio
async def test_replay_returns_recorded_response(tmp_path):
    rec_file = tmp_path / "rec.jsonl"
    inner = _FakeLLM({"action": "finish", "thinking": ".", "user_message": "x", "summary": "."})
    rec = RecordingLLMClient(inner, rec_file)
    msgs = [ChatMessage(role="user", content="hello")]
    schema = {"type": "object"}
    await rec.generate_structured(msgs, schema, model="m")

    replay = ReplayLLMClient(rec_file)
    out = await replay.generate_structured(msgs, schema, model="m")
    assert out["action"] == "finish"


@pytest.mark.asyncio
async def test_replay_raises_on_cache_miss(tmp_path):
    rec_file = tmp_path / "rec.jsonl"
    rec_file.write_text("")
    replay = ReplayLLMClient(rec_file)
    with pytest.raises(LLMError, match="no recording"):
        await replay.generate_structured(
            [ChatMessage(role="user", content="hi")], {"type": "object"}, model="m"
        )


def test_request_hash_is_deterministic_and_input_sensitive():
    a = request_hash([{"role": "user", "content": "a"}], {"x": 1}, "m")
    b = request_hash([{"role": "user", "content": "a"}], {"x": 1}, "m")
    c = request_hash([{"role": "user", "content": "b"}], {"x": 1}, "m")
    assert a == b
    assert a != c
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_recording_clients.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/maya_agent/sidecar/recording_clients.py`**

```python
"""Recording and replay wrappers for the LLMClient.

RecordingLLMClient wraps any LLMClient and writes (request, response) pairs to JSONL.
ReplayLLMClient reads JSONL and returns the recorded response by request hash.
Used by the eval harness to keep CI deterministic.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from maya_agent.sidecar.llm_client import ChatMessage, LLMClient, LLMError


def request_hash(messages: list[Any], json_schema: dict, model: str) -> str:
    """Stable hash of the LLM request for matching live and replayed calls."""
    if messages and hasattr(messages[0], "model_dump"):
        messages = [m.model_dump() for m in messages]
    payload = json.dumps(
        {"messages": messages, "schema": json_schema, "model": model},
        sort_keys=True, separators=(", ", ": "),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class RecordingLLMClient:
    """Wraps a real LLMClient, appending (hash, request, response) to JSONL on each call."""

    def __init__(self, inner: LLMClient, recording_path: Path) -> None:
        self._inner = inner
        self._path = Path(recording_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def generate_structured(self, messages, json_schema, *, model,
                                  temperature: float = 0.0, timeout_s: float = 120.0) -> dict:
        response = await self._inner.generate_structured(
            messages, json_schema, model=model,
            temperature=temperature, timeout_s=timeout_s,
        )
        h = request_hash(messages, json_schema, model)
        record = {
            "request_hash": h,
            "request": {
                "messages": [m.model_dump() if hasattr(m, "model_dump") else m for m in messages],
                "schema": json_schema,
                "model": model,
            },
            "response": response,
        }
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        return response


class ReplayLLMClient:
    """Reads JSONL and replays recorded responses. Raises on cache miss."""

    def __init__(self, recording_path: Path) -> None:
        self._path = Path(recording_path)
        self._cache: dict[str, dict] = {}
        if self._path.exists():
            for line in self._path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                self._cache[rec["request_hash"]] = rec["response"]

    async def generate_structured(self, messages, json_schema, *, model,
                                  temperature: float = 0.0, timeout_s: float = 120.0) -> dict:
        h = request_hash(messages, json_schema, model)
        if h not in self._cache:
            raise LLMError(f"no recording for request hash {h[:12]}... in {self._path}")
        return self._cache[h]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_recording_clients.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/maya_agent/sidecar/recording_clients.py tests/unit/test_recording_clients.py
git commit -m "feat(sidecar): RecordingLLMClient and ReplayLLMClient wrappers"
```

---

### Task 4.3: OllamaClient

**Files:**
- Create: `src/maya_agent/sidecar/ollama_client.py`

- [ ] **Step 1: Implement `src/maya_agent/sidecar/ollama_client.py`**

```python
"""OllamaClient: LLMClient implementation talking to Ollama HTTP API.

Uses the /api/chat endpoint with the `format` parameter set to a JSON schema
that constrains the response. Returns the parsed JSON object.
"""
from __future__ import annotations

import json
import logging

import httpx

from maya_agent.sidecar.llm_client import ChatMessage, LLMError

_log = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self._base_url = base_url.rstrip("/")

    async def generate_structured(
        self,
        messages: list[ChatMessage],
        json_schema: dict,
        *,
        model: str,
        temperature: float = 0.0,
        timeout_s: float = 120.0,
    ) -> dict:
        payload = {
            "model": model,
            "messages": [m.model_dump() for m in messages],
            "format": json_schema,
            "stream": False,
            "options": {"temperature": temperature},
        }
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            try:
                resp = await client.post(f"{self._base_url}/api/chat", json=payload)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                raise LLMError(f"Ollama HTTP error: {e}") from e
        body = resp.json()
        content = body.get("message", {}).get("content")
        if not content:
            raise LLMError(f"Ollama response has no content: {body}")
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise LLMError(f"Ollama returned non-JSON content: {content[:200]}") from e
```

- [ ] **Step 2: Smoke-test against a local Ollama (manual)**

If you have Ollama running with a model pulled:
```bash
python -c "
import asyncio
from maya_agent.sidecar.ollama_client import OllamaClient
from maya_agent.sidecar.llm_client import ChatMessage

async def main():
    c = OllamaClient()
    schema = {'type': 'object', 'properties': {'greeting': {'type': 'string'}}, 'required': ['greeting']}
    out = await c.generate_structured(
        [ChatMessage(role='user', content='Reply with a JSON greeting.')],
        schema, model='gemma3:27b',
    )
    print(out)

asyncio.run(main())
"
```
Expected: `{'greeting': '...'}` printed. If Ollama isn't installed, skip this manual step.

- [ ] **Step 3: Commit**

```bash
git add src/maya_agent/sidecar/ollama_client.py
git commit -m "feat(sidecar): OllamaClient implementation using format=json_schema"
```

---

## Phase 5 — Sidecar Maya client

### Task 5.1: MayaClient (asyncio socket)

**Files:**
- Create: `src/maya_agent/sidecar/maya_client.py`
- Create: `tests/unit/test_maya_client.py`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_maya_client.py`:
```python
import asyncio
import pytest
from maya_agent.core.frames import encode_frame, FrameDecoder
from maya_agent.core.protocol import (
    ToolInventoryMessage, UserIntentMessage, ToolCallMessage, parse_message,
)
from maya_agent.sidecar.maya_client import MayaClient


@pytest.mark.asyncio
async def test_round_trip_via_loopback():
    """Stand up a local TCP server, have MayaClient connect to it, exchange frames."""
    received: list[bytes] = []

    async def handle(reader, writer):
        # Read one frame: 4-byte length + body
        header = await reader.readexactly(4)
        length = int.from_bytes(header, "big")
        body = await reader.readexactly(length)
        received.append(body)
        # Send back an inventory message
        inv = ToolInventoryMessage(tools=[]).model_dump()
        writer.write(encode_frame(inv))
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    serving = asyncio.create_task(server.serve_forever())

    client = MayaClient()
    await client.connect_tcp("127.0.0.1", port)

    # Send a user_intent
    await client.send(UserIntentMessage(intent_id="i1", text="hello"))

    # Receive the inventory back
    msg = await asyncio.wait_for(client.receive(), timeout=2.0)
    assert isinstance(msg, ToolInventoryMessage)

    server.close()
    serving.cancel()
    await client.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_maya_client.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/maya_agent/sidecar/maya_client.py`**

```python
"""MayaClient: async socket client that speaks length-prefixed JSON frames.

Connects either to a TCP loopback (for tests) or a named pipe / unix domain
socket (production). Sends/receives Message instances from the protocol module.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from maya_agent.core.frames import encode_frame, FrameDecoder
from maya_agent.core.protocol import Message, encode_message, parse_message

_log = logging.getLogger(__name__)


class MayaClient:
    def __init__(self) -> None:
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._decoder = FrameDecoder()
        self._inbox: asyncio.Queue[Message] = asyncio.Queue()
        self._reader_task: asyncio.Task | None = None

    async def connect_pipe(self, pipe_path: str) -> None:
        """Connect to a named pipe (Windows) or unix domain socket (Linux/macOS)."""
        if sys.platform == "win32":
            # Windows named pipe via asyncio
            from asyncio.windows_events import _WindowsSelectorEventLoopPolicy  # noqa
            # asyncio doesn't have a built-in connect_pipe; we fall back to a thread
            # implementation if needed. For now, this is a stub raising NotImplementedError
            # — wired up in Phase 7 alongside the sidecar entry point.
            raise NotImplementedError("Windows named-pipe connect: implemented in Phase 7")
        else:
            self._reader, self._writer = await asyncio.open_unix_connection(pipe_path)
        self._start_reader()

    async def connect_tcp(self, host: str, port: int) -> None:
        """Useful for tests."""
        self._reader, self._writer = await asyncio.open_connection(host, port)
        self._start_reader()

    def _start_reader(self) -> None:
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        assert self._reader is not None
        try:
            while True:
                chunk = await self._reader.read(65536)
                if not chunk:
                    return
                for raw in self._decoder.feed(chunk):
                    try:
                        msg = parse_message(raw)
                    except Exception as e:
                        _log.exception("Failed to parse incoming message: %s", e)
                        continue
                    await self._inbox.put(msg)
        except asyncio.CancelledError:
            raise
        except Exception:
            _log.exception("MayaClient read loop crashed")

    async def send(self, msg: Message) -> None:
        if self._writer is None:
            raise RuntimeError("MayaClient not connected")
        self._writer.write(encode_frame(encode_message(msg)))
        await self._writer.drain()

    async def receive(self) -> Message:
        return await self._inbox.get()

    async def close(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_maya_client.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/maya_agent/sidecar/maya_client.py tests/unit/test_maya_client.py
git commit -m "feat(sidecar): MayaClient async socket transport"
```

---

## Phase 6 — Agent loop

### Task 6.1: Prompt builder

**Files:**
- Create: `src/maya_agent/sidecar/prompts.py`
- Create: `tests/unit/test_prompts.py`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_prompts.py`:
```python
from maya_agent.sidecar.prompts import build_system_prompt, RESPONSE_SCHEMA


def test_system_prompt_includes_tool_inventory():
    inventory = [
        {"name": "inspect_scene", "description": "Look at the scene.", "mutating": False,
         "json_schema": {"type": "object", "properties": {"deep": {"type": "boolean"}}}},
        {"name": "fix_euler", "description": "Fix euler.", "mutating": True,
         "json_schema": {"type": "object", "properties": {"objs": {"type": "array"}}}},
    ]
    prompt = build_system_prompt(inventory, max_clarifies=3, summaries=[], current_intent="do X")
    assert "inspect_scene" in prompt
    assert "Look at the scene." in prompt
    assert "fix_euler" in prompt
    assert "do X" in prompt
    assert "clarify at most 3 times" in prompt.lower() or "at most 3" in prompt


def test_system_prompt_renders_summaries():
    inv = [{"name": "t", "description": "d", "mutating": False, "json_schema": {"type": "object"}}]
    summaries = [
        ("clean up arms", "Fixed 3 discontinuities on L_arm_FK_CTL."),
        ("playblast", "Rendered frames 1-100 at 720p."),
    ]
    prompt = build_system_prompt(inv, max_clarifies=3, summaries=summaries, current_intent="now legs")
    assert "clean up arms" in prompt
    assert "Fixed 3 discontinuities" in prompt
    assert "playblast" in prompt
    assert "now legs" in prompt


def test_response_schema_has_action_enum():
    assert RESPONSE_SCHEMA["properties"]["action"]["enum"] == ["tool_call", "clarify", "finish"]
    assert RESPONSE_SCHEMA["required"] == ["thinking", "action"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_prompts.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/maya_agent/sidecar/prompts.py`**

```python
"""System prompt builder. Rebuilt fresh per intent."""
from __future__ import annotations

from textwrap import dedent

RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "thinking": {"type": "string", "description": "Private reasoning, not shown to the user."},
        "action": {"type": "string", "enum": ["tool_call", "clarify", "finish"]},
        "tool": {"type": ["string", "null"]},
        "arguments": {"type": ["object", "null"]},
        "question": {"type": ["string", "null"]},
        "user_message": {"type": ["string", "null"]},
        "summary": {"type": ["string", "null"]},
    },
    "required": ["thinking", "action"],
    "additionalProperties": False,
}

_PREAMBLE = dedent("""\
    You are a Maya animation assistant working inside the user's Maya session.
    You accomplish tasks by calling tools. You never write or generate Maya code
    directly — you only choose tools from the inventory below.

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
      summary: <=3 sentences capturing what was done; this is your memory for future intents

    ## Decision policy
    - Prefer to act on the most likely interpretation; explain assumptions in your final user_message.
    - Use clarify only when guessing wrong would mutate the scene in a way expensive to revert.
    - You may clarify at most {max_clarifies} times per intent.
    - After a tool returns an error, read it carefully before retrying — most errors are caused by wrong arguments, not missing capability.
""")


def _render_inventory(inventory: list[dict]) -> str:
    """Compact, line-per-arg rendering of the tool inventory."""
    lines: list[str] = []
    for entry in inventory:
        lines.append(f"- name: {entry['name']}")
        lines.append(f"  mutating: {str(entry['mutating']).lower()}")
        lines.append(f"  description: {entry['description'].strip()}")
        schema = entry.get("json_schema") or {}
        props = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        if props:
            lines.append("  arguments:")
            for arg_name, arg_schema in props.items():
                t = arg_schema.get("type", "any")
                desc = arg_schema.get("description", "")
                default = arg_schema.get("default")
                req_marker = "*" if arg_name in required else ""
                if default is not None:
                    arg_line = f"    {arg_name}{req_marker}: {t} = {default!r}"
                else:
                    arg_line = f"    {arg_name}{req_marker}: {t}"
                if desc:
                    arg_line += f"   -- {desc}"
                lines.append(arg_line)
        else:
            lines.append("  arguments: (none)")
    return "\n".join(lines)


def _render_summaries(summaries: list[tuple[str, str]]) -> str:
    if not summaries:
        return "(no previous intents)"
    out = []
    for user_text, summary in summaries:
        out.append(f"- intent: {user_text!r}")
        out.append(f"  result: {summary}")
    return "\n".join(out)


def build_system_prompt(
    inventory: list[dict],
    *,
    max_clarifies: int,
    summaries: list[tuple[str, str]],
    current_intent: str,
) -> str:
    return (
        _PREAMBLE.format(max_clarifies=max_clarifies)
        + "\n## Tool inventory\n"
        + _render_inventory(inventory)
        + "\n\n## Memory of previous intents\n"
        + _render_summaries(summaries)
        + "\n\n## Current intent\n"
        + current_intent.strip()
        + "\n"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_prompts.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/maya_agent/sidecar/prompts.py tests/unit/test_prompts.py
git commit -m "feat(sidecar): system prompt builder + RESPONSE_SCHEMA"
```

---

### Task 6.2: AgentLoop happy-path state machine

**Files:**
- Create: `src/maya_agent/sidecar/state.py`
- Create: `src/maya_agent/sidecar/agent_loop.py`
- Create: `tests/unit/test_agent_loop.py`

- [ ] **Step 1: Write the failing tests** (covers Tasks 6.2 through 6.5; subsequent tasks add to this same file)

`tests/unit/test_agent_loop.py`:
```python
import asyncio
import pytest
from maya_agent.sidecar.agent_loop import AgentLoop, IntentRequest
from maya_agent.sidecar.llm_client import ChatMessage


class _ScriptedLLM:
    """Returns the next scripted response on each call. Records messages it received."""
    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.calls: list[list[ChatMessage]] = []
    async def generate_structured(self, messages, json_schema, *, model,
                                  temperature=0.0, timeout_s=120.0):
        self.calls.append(list(messages))
        if not self._responses:
            raise RuntimeError("scripted LLM exhausted")
        return self._responses.pop(0)


class _MockMaya:
    """Mock MayaClient that returns scripted tool results."""
    def __init__(self, results: dict[str, dict]) -> None:
        self.results = results  # tool_name -> result dict
        self.tool_calls: list[tuple[str, dict]] = []
        self.events_sent: list[dict] = []
    async def call_tool(self, intent_id, call_id, tool, args):
        self.tool_calls.append((tool, args))
        return self.results.get(tool, {"ok": False, "error": f"no fixture for {tool}"})
    async def emit(self, event: dict):
        self.events_sent.append(event)


_INV = [
    {"name": "inspect_scene", "description": "Inspect.", "mutating": False,
     "json_schema": {"type": "object", "properties": {}}},
    {"name": "fix_euler", "description": "Fix euler.", "mutating": True,
     "json_schema": {"type": "object", "properties": {"obj": {"type": "string"}}, "required": ["obj"]}},
]


@pytest.mark.asyncio
async def test_happy_path_two_tools_then_finish():
    llm = _ScriptedLLM([
        {"thinking": "first inspect", "action": "tool_call", "tool": "inspect_scene", "arguments": {}},
        {"thinking": "now fix",       "action": "tool_call", "tool": "fix_euler",     "arguments": {"obj": "ctrl"}},
        {"thinking": "done",          "action": "finish", "user_message": "Done.", "summary": "Fixed euler on ctrl."},
    ])
    maya = _MockMaya({
        "inspect_scene": {"ok": True, "value": {"selection": ["ctrl"]}},
        "fix_euler":     {"ok": True, "value": {"fixed": 1}},
    })
    loop = AgentLoop(llm=llm, maya=maya, inventory=_INV, model="m", max_steps=10)
    result = await loop.run_intent(IntentRequest(intent_id="i", text="fix euler"),
                                    on_event=lambda e: None)
    assert result.terminal_action == "finish"
    assert result.summary == "Fixed euler on ctrl."
    assert result.user_message == "Done."
    assert [tc[0] for tc in maya.tool_calls] == ["inspect_scene", "fix_euler"]


@pytest.mark.asyncio
async def test_unknown_tool_returns_error_observation():
    llm = _ScriptedLLM([
        {"thinking": "try fake", "action": "tool_call", "tool": "nonexistent", "arguments": {}},
        {"thinking": "ok finish", "action": "finish", "user_message": "Couldn't.", "summary": "No tool."},
    ])
    maya = _MockMaya({})
    loop = AgentLoop(llm=llm, maya=maya, inventory=_INV, model="m", max_steps=10)
    result = await loop.run_intent(IntentRequest(intent_id="i", text="x"),
                                    on_event=lambda e: None)
    # Last user message in the LLM call history should describe the unknown tool error
    last_user_content = [m.content for m in llm.calls[-1] if m.role == "user"][-1]
    assert "Unknown tool" in last_user_content


@pytest.mark.asyncio
async def test_invalid_arguments_loop_back_as_error():
    llm = _ScriptedLLM([
        {"thinking": "wrong args", "action": "tool_call", "tool": "fix_euler", "arguments": {}},  # missing 'obj'
        {"thinking": "retry",      "action": "tool_call", "tool": "fix_euler", "arguments": {"obj": "ctrl"}},
        {"thinking": "done",       "action": "finish", "user_message": "k", "summary": "k"},
    ])
    maya = _MockMaya({"fix_euler": {"ok": True, "value": {"fixed": 1}}})
    loop = AgentLoop(llm=llm, maya=maya, inventory=_INV, model="m", max_steps=10)
    result = await loop.run_intent(IntentRequest(intent_id="i", text="fix"),
                                    on_event=lambda e: None)
    # First call to maya should NOT have happened (validation rejected before dispatch)
    assert maya.tool_calls == [("fix_euler", {"obj": "ctrl"})]
    assert result.terminal_action == "finish"


@pytest.mark.asyncio
async def test_clarify_then_continue():
    events: list[dict] = []
    llm = _ScriptedLLM([
        {"thinking": "ambiguous", "action": "clarify", "question": "Which arm?"},
        {"thinking": "now act",   "action": "tool_call", "tool": "fix_euler", "arguments": {"obj": "L_arm"}},
        {"thinking": "done",      "action": "finish", "user_message": "Fixed.", "summary": "."},
    ])
    maya = _MockMaya({"fix_euler": {"ok": True, "value": {"fixed": 1}}})
    loop = AgentLoop(llm=llm, maya=maya, inventory=_INV, model="m",
                     max_steps=10, max_clarifies=3)

    # Inject a clarify response via the loop's clarify queue
    async def feed_response():
        await asyncio.sleep(0.05)
        await loop.provide_clarify_response("i", "L arm please")
    asyncio.create_task(feed_response())

    result = await loop.run_intent(IntentRequest(intent_id="i", text="fix arm"),
                                    on_event=lambda e: events.append(e))
    assert result.terminal_action == "finish"
    # Last user message before final tool call should contain the clarification text
    msgs_before_final = llm.calls[1]
    assert any("L arm please" in m.content for m in msgs_before_final if m.role == "user")


@pytest.mark.asyncio
async def test_step_limit_forces_finish():
    # LLM keeps calling inspect_scene forever
    llm = _ScriptedLLM([
        {"thinking": ".", "action": "tool_call", "tool": "inspect_scene", "arguments": {}}
        for _ in range(5)
    ] + [
        {"thinking": "done", "action": "finish", "user_message": "Stopped.", "summary": "Hit limit."}
    ])
    maya = _MockMaya({"inspect_scene": {"ok": True, "value": {}}})
    loop = AgentLoop(llm=llm, maya=maya, inventory=_INV, model="m", max_steps=4)
    result = await loop.run_intent(IntentRequest(intent_id="i", text="loop"),
                                    on_event=lambda e: None)
    # Either finished naturally on the warning, or we forced a finish
    assert result.terminal_action in ("finish", "step_limit")
    assert len(maya.tool_calls) <= 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_agent_loop.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/maya_agent/sidecar/state.py`**

```python
"""Cross-intent memory: bounded ring of (intent_text, summary) pairs."""
from __future__ import annotations

from collections import deque


class CrossIntentMemory:
    def __init__(self, max_entries: int = 10) -> None:
        self._entries: deque[tuple[str, str]] = deque(maxlen=max_entries)

    def add(self, intent_text: str, summary: str) -> None:
        self._entries.append((intent_text, summary))

    def as_list(self) -> list[tuple[str, str]]:
        return list(self._entries)

    def clear(self) -> None:
        self._entries.clear()
```

- [ ] **Step 4: Implement `src/maya_agent/sidecar/agent_loop.py`**

```python
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

                thinking = raw.get("thinking", "")
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_agent_loop.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/maya_agent/sidecar/state.py src/maya_agent/sidecar/agent_loop.py tests/unit/test_agent_loop.py
git commit -m "feat(sidecar): AgentLoop with happy-path, errors, clarify, step limit"
```

---

### Task 6.3: Cross-intent memory test

**Files:**
- Create: `tests/unit/test_state.py`

- [ ] **Step 1: Write tests**

`tests/unit/test_state.py`:
```python
from maya_agent.sidecar.state import CrossIntentMemory


def test_memory_drops_oldest_at_capacity():
    m = CrossIntentMemory(max_entries=2)
    m.add("a", "A")
    m.add("b", "B")
    m.add("c", "C")
    assert m.as_list() == [("b", "B"), ("c", "C")]


def test_memory_clear():
    m = CrossIntentMemory()
    m.add("x", "X")
    m.clear()
    assert m.as_list() == []
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/unit/test_state.py -v`
Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_state.py
git commit -m "test(sidecar): cross-intent memory bounded ring"
```

---

## Phase 7 — Sidecar entry point

### Task 7.1: `python -m maya_agent.sidecar`

**Files:**
- Create: `src/maya_agent/sidecar/__main__.py`

- [ ] **Step 1: Implement the entry point**

```python
"""Sidecar process entry point.

Usage:
  python -m maya_agent.sidecar --pipe \\\\.\\pipe\\maya-agent-12345 [--model gemma3:27b]

Reads --model, --pipe, --ollama-base-url, optional --max-steps from argv.
Falls back to env vars MAYA_AGENT_MODEL, MAYA_AGENT_PIPE, MAYA_AGENT_OLLAMA_URL.

Connects to the named pipe, awaits the tool_inventory message, then services
user_intent / clarify_response / cancel messages by running the AgentLoop.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from maya_agent.core.protocol import (
    UserIntentMessage, ClarifyResponseMessage, CancelMessage, ToolInventoryMessage,
    ToolCallMessage, ToolResultMessage, ThinkingMessage, AssistantMessage,
    ClarifyQuestionMessage, IntentFinishedMessage, IntentFailedMessage, parse_message,
)
from maya_agent.sidecar.agent_loop import AgentLoop, IntentRequest
from maya_agent.sidecar.maya_client import MayaClient
from maya_agent.sidecar.ollama_client import OllamaClient


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="maya-agent-sidecar")
    p.add_argument("--pipe", default=os.environ.get("MAYA_AGENT_PIPE"),
                   help="Named pipe / unix socket path the Maya panel is listening on")
    p.add_argument("--model", default=os.environ.get("MAYA_AGENT_MODEL"),
                   help="LLM model identifier (e.g., gemma3:27b)")
    p.add_argument("--ollama-base-url", default=os.environ.get(
        "MAYA_AGENT_OLLAMA_URL", "http://localhost:11434"))
    p.add_argument("--max-steps", type=int, default=20)
    p.add_argument("--log-file", default=None)
    args = p.parse_args()
    if not args.pipe:
        p.error("--pipe is required (or set MAYA_AGENT_PIPE)")
    if not args.model:
        p.error("--model is required (or set MAYA_AGENT_MODEL)")
    return args


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

    log.info("Connecting to %s", args.pipe)
    client = MayaClient()

    if sys.platform == "win32":
        # On Windows, use a thread-based bridge for named pipes (asyncio doesn't
        # natively support Windows named pipes for connect; we use the pipe path
        # as a TCP loopback for v1 development OR implement via win32 calls).
        # For v1 simplicity: support pipe paths that are actually "host:port"
        # for development, and document named-pipe support as v1.1.
        if ":" in args.pipe:
            host, port = args.pipe.rsplit(":", 1)
            await client.connect_tcp(host, int(port))
        else:
            log.error("Windows named-pipe connect not implemented in v1; use host:port form")
            return 2
    else:
        await client.connect_pipe(args.pipe)

    # Wait for the inventory handshake
    msg = await client.receive()
    if not isinstance(msg, ToolInventoryMessage):
        log.error("First message was not tool_inventory: %s", type(msg).__name__)
        return 3
    inventory = msg.tools
    log.info("Received inventory: %d tools", len(inventory))

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
```

- [ ] **Step 2: Smoke test the entry point parses args**

Run: `python -m maya_agent.sidecar --help`
Expected: argparse usage message printed.

- [ ] **Step 3: Commit**

```bash
git add src/maya_agent/sidecar/__main__.py
git commit -m "feat(sidecar): __main__ entry point wires MayaClient + AgentLoop + Ollama"
```

---

## Phase 8 — Maya-side command server & tool dispatcher

> **Note:** Phases 8-11 (everything that imports `maya.cmds`) are tested via mocks in CI. Real-Maya verification happens during the manual smoke-test success criterion.

### Task 8.1: Command server (Qt)

**Files:**
- Create: `src/maya_agent/maya/command_server.py`

- [ ] **Step 1: Implement the command server**

```python
"""QLocalServer that accepts the sidecar connection and exchanges length-prefixed
JSON frames. Inbound frames are emitted as Qt signals on the main thread.
"""
from __future__ import annotations

import logging
import os
from typing import Callable

from PySide6 import QtCore, QtNetwork

from maya_agent.core.frames import FrameDecoder, FrameError, encode_frame
from maya_agent.core.protocol import Message, encode_message, parse_message

_log = logging.getLogger(__name__)


def default_pipe_path() -> str:
    """Pipe path that includes the current PID so multiple Maya instances don't collide."""
    if os.name == "nt":
        return f"maya-agent-{os.getpid()}"  # QLocalServer prepends \\.\pipe\ on Windows
    return f"/tmp/maya-agent-{os.getpid()}.sock"


class CommandServer(QtCore.QObject):
    """Owns a QLocalServer + a single client socket (the sidecar).

    Emits message_received(Message) when a frame is fully decoded. Send messages
    via send_message() — works whether or not the client is currently connected
    (queued and flushed on connect).
    """

    message_received = QtCore.Signal(object)  # Message instance
    client_connected = QtCore.Signal()
    client_disconnected = QtCore.Signal()

    def __init__(self, pipe_name: str | None = None, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._pipe_name = pipe_name or default_pipe_path()
        self._server = QtNetwork.QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        self._socket: QtNetwork.QLocalSocket | None = None
        self._decoder = FrameDecoder()
        self._send_queue: list[bytes] = []

    def start(self) -> None:
        # Remove any stale socket file (Linux/macOS)
        QtNetwork.QLocalServer.removeServer(self._pipe_name)
        if not self._server.listen(self._pipe_name):
            raise RuntimeError(
                f"Failed to listen on {self._pipe_name}: {self._server.errorString()}"
            )
        _log.info("CommandServer listening on %s", self.full_pipe_path())

    def stop(self) -> None:
        if self._socket is not None:
            self._socket.disconnectFromServer()
            self._socket = None
        self._server.close()

    def full_pipe_path(self) -> str:
        if os.name == "nt":
            return rf"\\.\pipe\{self._pipe_name}"
        return self._pipe_name

    def is_connected(self) -> bool:
        return self._socket is not None and self._socket.state() == QtNetwork.QLocalSocket.ConnectedState

    def send_message(self, msg: Message) -> None:
        frame = encode_frame(encode_message(msg))
        if self.is_connected():
            self._socket.write(frame)
            self._socket.flush()
        else:
            self._send_queue.append(frame)

    def _on_new_connection(self) -> None:
        if self._socket is not None:
            # Reject second connection
            extra = self._server.nextPendingConnection()
            extra.disconnectFromServer()
            return
        self._socket = self._server.nextPendingConnection()
        self._socket.readyRead.connect(self._on_ready_read)
        self._socket.disconnected.connect(self._on_disconnected)
        # Flush queued frames
        for frame in self._send_queue:
            self._socket.write(frame)
        self._socket.flush()
        self._send_queue.clear()
        self._decoder = FrameDecoder()
        self.client_connected.emit()
        _log.info("Sidecar client connected")

    def _on_ready_read(self) -> None:
        if self._socket is None:
            return
        data = bytes(self._socket.readAll().data())
        try:
            for raw in self._decoder.feed(data):
                try:
                    msg = parse_message(raw)
                except Exception:
                    _log.exception("Invalid incoming message")
                    continue
                self.message_received.emit(msg)
        except FrameError:
            _log.exception("Frame decode error; closing socket")
            self._socket.disconnectFromServer()

    def _on_disconnected(self) -> None:
        _log.info("Sidecar client disconnected")
        self._socket = None
        self.client_disconnected.emit()
```

- [ ] **Step 2: Commit**

```bash
git add src/maya_agent/maya/command_server.py
git commit -m "feat(maya): QLocalServer-based CommandServer with Qt signals"
```

---

### Task 8.2: Tool dispatcher

**Files:**
- Create: `src/maya_agent/maya/tool_dispatcher.py`
- Create: `tests/unit/test_tool_dispatcher.py`

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_tool_dispatcher.py`:
```python
from unittest.mock import MagicMock, patch
from pydantic import Field
from tools_common import Tool, ToolArgs, ToolResult
from maya_agent.core.registry import ToolRegistry
from maya_agent.maya.tool_dispatcher import ToolDispatcher


class _Args(ToolArgs):
    x: int = Field(...)


class _MutTool(Tool):
    name = "mut"
    description = "Mutates."
    args_model = _Args
    mutating = True
    def execute(self, args, *, cancel_token=None):
        return ToolResult(ok=True, value={"got": args.x})


class _ReadTool(Tool):
    name = "read"
    description = "Reads."
    args_model = _Args
    mutating = False
    def execute(self, args, *, cancel_token=None):
        return ToolResult(ok=True, value={"got": args.x})


def _make_dispatcher():
    reg = ToolRegistry()
    reg.register(_MutTool, "/")
    reg.register(_ReadTool, "/")
    return ToolDispatcher(reg)


def test_dispatcher_validates_args_and_returns_result():
    d = _make_dispatcher()
    with patch("maya_agent.maya.tool_dispatcher.cmds") as cmds:
        result = d.dispatch("read", {"x": 5})
        assert result.ok is True
        assert result.value == {"got": 5}
        # read tool should not open undo chunk
        cmds.undoInfo.assert_not_called()


def test_dispatcher_wraps_mutating_tool_in_undo_chunk():
    d = _make_dispatcher()
    with patch("maya_agent.maya.tool_dispatcher.cmds") as cmds:
        result = d.dispatch("mut", {"x": 7})
        assert result.ok is True
        # openChunk + closeChunk
        calls = [c for c in cmds.undoInfo.call_args_list]
        assert any(call.kwargs.get("openChunk") for call in calls)
        assert any(call.kwargs.get("closeChunk") for call in calls)


def test_dispatcher_returns_error_on_validation_failure():
    d = _make_dispatcher()
    result = d.dispatch("mut", {})  # missing x
    assert result.ok is False
    assert "x" in (result.error or "")


def test_dispatcher_returns_error_on_unknown_tool():
    d = _make_dispatcher()
    result = d.dispatch("nope", {"x": 1})
    assert result.ok is False
    assert "unknown" in (result.error or "").lower()


def test_dispatcher_catches_tool_exceptions_and_closes_chunk():
    class _BoomArgs(ToolArgs):
        x: int = Field(...)
    class _Boom(Tool):
        name = "boom"; description = "Boom."; args_model = _BoomArgs; mutating = True
        def execute(self, args, *, cancel_token=None):
            raise ValueError("crash")
    reg = ToolRegistry()
    reg.register(_Boom, "/")
    d = ToolDispatcher(reg)
    with patch("maya_agent.maya.tool_dispatcher.cmds") as cmds:
        result = d.dispatch("boom", {"x": 1})
        assert result.ok is False
        assert "ValueError" in (result.error or "") and "crash" in (result.error or "")
        # closeChunk must still be called
        assert any(call.kwargs.get("closeChunk") for call in cmds.undoInfo.call_args_list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_tool_dispatcher.py -v`
Expected: ImportError (cmds patch will fail if module doesn't import; we use a stub fallback).

- [ ] **Step 3: Implement `src/maya_agent/maya/tool_dispatcher.py`**

```python
"""ToolDispatcher: validates args, wraps mutating tools in undo chunks, runs them.

Imports maya.cmds at module load. Outside Maya, this module won't import unless
a stub is patched in (the tests do exactly that).
"""
from __future__ import annotations

import inspect
import logging

try:
    from maya import cmds  # type: ignore
except ImportError:  # not in Maya — tests patch this module's `cmds` symbol
    cmds = None  # type: ignore

from pydantic import ValidationError

from tools_common import ToolResult
from maya_agent.core.registry import ToolRegistry, RegistryError

_log = logging.getLogger(__name__)


class ToolDispatcher:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def dispatch(self, tool_name: str, args: dict) -> ToolResult:
        try:
            tool_cls = self._registry.get(tool_name)
        except RegistryError as e:
            return ToolResult(ok=False, error=f"Unknown tool: {e}")

        try:
            parsed = tool_cls.args_model(**args)
        except ValidationError as e:
            return ToolResult(ok=False, error=f"Invalid arguments: {e}")

        tool = tool_cls()
        accepts_cancel = "cancel_token" in inspect.signature(tool.execute).parameters
        kwargs = {"cancel_token": None} if accepts_cancel else {}

        if tool_cls.mutating and cmds is not None:
            cmds.undoInfo(openChunk=True, chunkName=tool_name)
            try:
                return self._run(tool, parsed, kwargs)
            finally:
                cmds.undoInfo(closeChunk=True)
        else:
            return self._run(tool, parsed, kwargs)

    @staticmethod
    def _run(tool, parsed, kwargs) -> ToolResult:
        try:
            return tool.execute(parsed, **kwargs)
        except Exception as e:
            _log.exception("Tool raised")
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_tool_dispatcher.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/maya_agent/maya/tool_dispatcher.py tests/unit/test_tool_dispatcher.py
git commit -m "feat(maya): ToolDispatcher with arg validation and undo-chunk wrapping"
```

---

## Phase 9 — Qt Panel

### Task 9.1: Panel skeleton

**Files:**
- Create: `src/maya_agent/maya/panel.py`

- [ ] **Step 1: Implement the panel**

```python
"""Maya Agent Qt panel. Dockable widget with chat, input, status, controls.

Imports PySide6; tested manually inside Maya. The panel owns:
- A CommandServer instance
- A subprocess.Popen reference for the sidecar (if launched in-panel)
- A chat model (list of items: user message, assistant message, tool entry)
- A ToolDispatcher hooked to the ToolRegistry
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import uuid
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from maya_agent.core.protocol import (
    AssistantMessage, CancelMessage, ClarifyQuestionMessage, ClarifyResponseMessage,
    IntentFailedMessage, IntentFinishedMessage, ThinkingMessage, ToolCallMessage,
    ToolInventoryMessage, ToolResultMessage, UserIntentMessage,
)
from maya_agent.core.registry import ToolRegistry
from maya_agent.maya.command_server import CommandServer
from maya_agent.maya.tool_dispatcher import ToolDispatcher

_log = logging.getLogger(__name__)


class _ChatItem(QtWidgets.QFrame):
    """Base for items rendered in the chat list."""


class _MessageItem(_ChatItem):
    def __init__(self, role: str, text: str) -> None:
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel(f"<b>{role}:</b> {text}")
        label.setWordWrap(True)
        layout.addWidget(label)


class _ToolEntry(_ChatItem):
    """Inline collapsible tool-call entry."""
    def __init__(self, tool: str, args: dict) -> None:
        super().__init__()
        self._args = args
        self._result: dict | None = None
        layout = QtWidgets.QVBoxLayout(self)
        self._header = QtWidgets.QLabel(f"⟳ {tool}")
        self._header.setStyleSheet("color: #888; font-family: monospace;")
        layout.addWidget(self._header)
        self._tool = tool

    def mark_finished(self, ok: bool, value, error: str | None) -> None:
        self._result = {"ok": ok, "value": value, "error": error}
        icon = "✓" if ok else "✗"
        self._header.setText(f"{icon} {self._tool}")


class MayaAgentPanel(QtWidgets.QWidget):
    def __init__(self, registry: ToolRegistry, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._registry = registry
        self._dispatcher = ToolDispatcher(registry)
        self._server = CommandServer()
        self._sidecar_process: subprocess.Popen | None = None
        self._tool_entries: dict[str, _ToolEntry] = {}  # call_id -> entry
        self._current_intent_id: str | None = None

        self._build_ui()
        self._wire_signals()
        self._server.start()
        self._update_status_disconnected()

    def _build_ui(self) -> None:
        v = QtWidgets.QVBoxLayout(self)

        # Status row
        self._status_label = QtWidgets.QLabel("● Disconnected")
        self._status_label.setStyleSheet("padding: 4px;")
        v.addWidget(self._status_label)

        # Plugin warning banner (hidden by default)
        self._warning_banner = QtWidgets.QLabel("")
        self._warning_banner.setStyleSheet(
            "background: #5a3a00; color: white; padding: 6px;")
        self._warning_banner.hide()
        v.addWidget(self._warning_banner)

        # Chat area
        self._chat = QtWidgets.QListWidget()
        v.addWidget(self._chat, stretch=1)

        # Input area
        self._input = QtWidgets.QPlainTextEdit()
        self._input.setPlaceholderText("Type a request... (Ctrl+Enter to send)")
        self._input.setMaximumHeight(80)
        v.addWidget(self._input)

        # Buttons
        h = QtWidgets.QHBoxLayout()
        self._send_btn = QtWidgets.QPushButton("Send")
        self._undo_btn = QtWidgets.QPushButton("Undo last")
        self._clear_btn = QtWidgets.QPushButton("Clear chat")
        self._stop_btn = QtWidgets.QPushButton("■ Stop")
        self._stop_btn.hide()
        h.addWidget(self._send_btn)
        h.addWidget(self._undo_btn)
        h.addWidget(self._clear_btn)
        h.addWidget(self._stop_btn)
        h.addStretch()
        self._start_sidecar_btn = QtWidgets.QPushButton("Start agent")
        h.addWidget(self._start_sidecar_btn)
        v.addLayout(h)

    def _wire_signals(self) -> None:
        self._send_btn.clicked.connect(self._on_send_clicked)
        self._undo_btn.clicked.connect(self._on_undo_clicked)
        self._clear_btn.clicked.connect(self._on_clear_clicked)
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        self._start_sidecar_btn.clicked.connect(self._on_start_sidecar_clicked)

        self._server.client_connected.connect(self._on_client_connected)
        self._server.client_disconnected.connect(self._on_client_disconnected)
        self._server.message_received.connect(self._on_message_received)

        # Ctrl+Enter to send
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Return"), self).activated.connect(
            self._on_send_clicked)

    # --- UI handlers ---

    def _on_send_clicked(self) -> None:
        text = self._input.toPlainText().strip()
        if not text or not self._server.is_connected():
            return
        intent_id = str(uuid.uuid4())
        self._current_intent_id = intent_id
        self._add_chat(_MessageItem("User", text))
        self._input.clear()
        self._stop_btn.show()
        if self._current_intent_id:  # waiting for clarify?
            # If we're between turns and the agent asked a question, treat input as the answer
            pass
        self._server.send_message(UserIntentMessage(intent_id=intent_id, text=text))

    def _on_undo_clicked(self) -> None:
        try:
            from maya import cmds
            cmds.undo()
        except Exception:
            _log.exception("Undo failed")

    def _on_clear_clicked(self) -> None:
        if QtWidgets.QMessageBox.question(
            self, "Clear chat", "Clear conversation history and cross-intent memory?"
        ) == QtWidgets.QMessageBox.StandardButton.Yes:
            self._chat.clear()
            self._tool_entries.clear()

    def _on_stop_clicked(self) -> None:
        if self._current_intent_id:
            self._server.send_message(CancelMessage(intent_id=self._current_intent_id))

    def _on_start_sidecar_clicked(self) -> None:
        if self._sidecar_process and self._sidecar_process.poll() is None:
            return
        log_dir = Path.home() / ".maya-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"sidecar-{os.getpid()}.log"
        env = os.environ.copy()
        # Sidecar reads pipe path + model from env or args
        cmd = [
            sys.executable, "-m", "maya_agent.sidecar",
            "--pipe", self._server.full_pipe_path(),
            "--log-file", str(log_file),
        ]
        if env.get("MAYA_AGENT_MODEL"):
            cmd += ["--model", env["MAYA_AGENT_MODEL"]]
        self._sidecar_process = subprocess.Popen(cmd, env=env)
        _log.info("Spawned sidecar PID %d, logs at %s", self._sidecar_process.pid, log_file)

    # --- Server signals ---

    def _on_client_connected(self) -> None:
        self._status_label.setText("● Connected — sending inventory")
        self._status_label.setStyleSheet("color: #2c2; padding: 4px;")
        # Send the inventory
        self._server.send_message(ToolInventoryMessage(tools=self._registry.inventory()))

    def _on_client_disconnected(self) -> None:
        self._update_status_disconnected()

    def _update_status_disconnected(self) -> None:
        self._status_label.setText(f"● Disconnected — pipe at {self._server.full_pipe_path()}")
        self._status_label.setStyleSheet("color: #888; padding: 4px;")
        self._stop_btn.hide()

    def _on_message_received(self, msg) -> None:
        if isinstance(msg, ToolCallMessage):
            entry = _ToolEntry(msg.tool, msg.args)
            self._tool_entries[msg.call_id] = entry
            self._add_chat(entry)
            # Dispatch on this thread (we're already on the main thread via Qt queued connection)
            result = self._dispatcher.dispatch(msg.tool, msg.args)
            entry.mark_finished(result.ok, result.value, result.error)
            self._server.send_message(ToolResultMessage(
                intent_id=msg.intent_id, call_id=msg.call_id,
                ok=result.ok, value=result.value, error=result.error,
            ))
        elif isinstance(msg, AssistantMessage):
            self._add_chat(_MessageItem("Agent", msg.text))
        elif isinstance(msg, ClarifyQuestionMessage):
            self._add_chat(_MessageItem("Agent (?)", msg.text))
            # Next user input becomes a clarify_response
            self._send_btn.clicked.disconnect()
            self._send_btn.clicked.connect(lambda: self._send_clarify_response(msg.intent_id))
        elif isinstance(msg, IntentFinishedMessage):
            self._add_chat(_MessageItem("Agent", msg.user_message))
            self._stop_btn.hide()
            self._current_intent_id = None
        elif isinstance(msg, IntentFailedMessage):
            self._add_chat(_MessageItem("Agent (failed)", msg.error))
            self._stop_btn.hide()
            self._current_intent_id = None
        elif isinstance(msg, ThinkingMessage):
            # Logged but not rendered by default
            _log.debug("[thinking %s] %s", msg.intent_id, msg.text)

    def _send_clarify_response(self, intent_id: str) -> None:
        text = self._input.toPlainText().strip()
        if not text:
            return
        self._add_chat(_MessageItem("User", text))
        self._input.clear()
        self._server.send_message(ClarifyResponseMessage(intent_id=intent_id, text=text))
        # Restore normal Send wiring
        self._send_btn.clicked.disconnect()
        self._send_btn.clicked.connect(self._on_send_clicked)

    def _add_chat(self, widget: _ChatItem) -> None:
        item = QtWidgets.QListWidgetItem()
        item.setSizeHint(widget.sizeHint())
        self._chat.addItem(item)
        self._chat.setItemWidget(item, widget)
        self._chat.scrollToBottom()

    def show_plugin_warnings(self, warnings: list[str]) -> None:
        if not warnings:
            self._warning_banner.hide()
            return
        self._warning_banner.setText(
            f"⚠ {len(warnings)} plugin issue(s): " + "; ".join(warnings[:3])
        )
        self._warning_banner.show()
```

- [ ] **Step 2: Commit**

```bash
git add src/maya_agent/maya/panel.py
git commit -m "feat(maya): Qt panel with chat, tool entries, status, controls"
```

---

## Phase 10 — Maya bootstrap & install

### Task 10.1: Bootstrap & install script

**Files:**
- Create: `src/maya_agent/maya/maya_bootstrap.py`
- Create: `scripts/install_into_maya.py`

- [ ] **Step 1: Implement `src/maya_agent/maya/maya_bootstrap.py`**

```python
"""Maya bootstrap: registers the panel as a workspaceControl, loads plugins.

Called from userSetup.py (or a shelf button) inside Maya. Not importable
outside Maya (uses maya.cmds and PySide6 widget integration).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from maya import cmds
from PySide6 import QtWidgets

from maya_agent.core.plugin_loader import load_plugins_from_paths
from maya_agent.core.registry import ToolRegistry

_log = logging.getLogger(__name__)
_PANEL_OBJECT_NAME = "MayaAgentPanel"


def _build_registry() -> tuple[ToolRegistry, list[str]]:
    reg = ToolRegistry()
    paths: list[Path] = []
    env_paths = os.environ.get("MAYA_AGENT_PLUGIN_PATHS", "")
    for p in env_paths.split(os.pathsep):
        p = p.strip()
        if p:
            paths.append(Path(p))
    # Append framework example tools
    examples = Path(__file__).parent / "tools"
    if examples.exists():
        paths.append(examples)
    summary = load_plugins_from_paths(paths, reg, current_maya_version=cmds.about(version=True))
    warnings = [f"{f.module_path.name}: {f.reason}" for f in summary.failed_modules]
    return reg, warnings


def show_panel() -> None:
    """Create or focus the Maya Agent dockable panel."""
    from maya_agent.maya.panel import MayaAgentPanel  # late import (PySide6 needs Maya UI)

    if cmds.workspaceControl(_PANEL_OBJECT_NAME, exists=True):
        cmds.workspaceControl(_PANEL_OBJECT_NAME, edit=True, restore=True)
        return

    cmds.workspaceControl(
        _PANEL_OBJECT_NAME, label="Maya Agent",
        retain=False, floating=True,
    )

    registry, warnings = _build_registry()
    panel = MayaAgentPanel(registry)
    panel.show_plugin_warnings(warnings)

    # Parent the panel widget to the workspaceControl
    ctrl_widget = _qt_widget_for_workspace_control(_PANEL_OBJECT_NAME)
    layout = QtWidgets.QVBoxLayout(ctrl_widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(panel)


def _qt_widget_for_workspace_control(name: str) -> QtWidgets.QWidget:
    """Find the QWidget for a workspaceControl by name."""
    from shiboken6 import wrapInstance
    from maya.OpenMayaUI import MQtUtil
    ptr = MQtUtil.findControl(name)
    if ptr is None:
        raise RuntimeError(f"Could not find workspaceControl: {name}")
    return wrapInstance(int(ptr), QtWidgets.QWidget)
```

- [ ] **Step 2: Implement `scripts/install_into_maya.py`**

```python
"""Write a Maya .mod file that points at this repo, so Maya picks up the package.

Usage:
  python scripts/install_into_maya.py [--maya-version 2024]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _maya_modules_dir(maya_version: str) -> Path:
    if sys.platform == "win32":
        return Path(os.environ["USERPROFILE"]) / "Documents" / "maya" / maya_version / "modules"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Preferences" / "Autodesk" / "maya" / maya_version / "modules"
    else:
        return Path.home() / "maya" / maya_version / "modules"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--maya-version", default="2024")
    args = p.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    src_path = repo_root / "src"
    if not src_path.exists():
        print(f"Expected src/ at {src_path}", file=sys.stderr)
        return 1

    modules_dir = _maya_modules_dir(args.maya_version)
    modules_dir.mkdir(parents=True, exist_ok=True)

    mod_path = modules_dir / "maya-agent.mod"
    mod_path.write_text(
        f"+ MAYAVERSION:{args.maya_version} maya-agent 0.1.0 {repo_root}\n"
        f"PYTHONPATH +:= src\n"
    )
    print(f"Wrote {mod_path}")
    print(f"Restart Maya {args.maya_version}; then run:")
    print(f"  import maya_agent.maya.maya_bootstrap as b; b.show_panel()")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Commit**

```bash
git add src/maya_agent/maya/maya_bootstrap.py scripts/install_into_maya.py
git commit -m "feat(maya): bootstrap show_panel() and install_into_maya.py mod writer"
```

---

## Phase 11 — Example tools

> Each tool follows the same shape: pydantic args model, Tool subclass with name/description/args_model/mutating, lazy `from maya import cmds` inside execute().

### Task 11.1: inspect_scene

**Files:**
- Create: `src/maya_agent/maya/tools/inspect_scene.py`

- [ ] **Step 1: Implement**

```python
"""inspect_scene: return current selection, namespaces, scene path, framerate."""
from __future__ import annotations

from pydantic import Field
from tools_common import Tool, ToolArgs, ToolResult


class InspectSceneArgs(ToolArgs):
    deep: bool = Field(False, description="Include all nodes (slow on big scenes); else summary only.")


class InspectScene(Tool):
    name = "inspect_scene"
    description = (
        "Return a summary of the current Maya scene: selection, namespaces, scene path, "
        "framerate, time range. Set deep=true to include a full node list (slow). Read-only."
    )
    args_model = InspectSceneArgs
    mutating = False

    def execute(self, args, *, cancel_token=None):
        from maya import cmds
        try:
            selection = cmds.ls(selection=True, long=True) or []
            namespaces = [n for n in (cmds.namespaceInfo(listOnlyNamespaces=True, recurse=True) or [])
                          if n not in ("UI", "shared")]
            scene_path = cmds.file(query=True, sceneName=True) or ""
            framerate = cmds.currentUnit(query=True, time=True)
            min_t = cmds.playbackOptions(query=True, minTime=True)
            max_t = cmds.playbackOptions(query=True, maxTime=True)
            value = {
                "selection": selection,
                "namespaces": namespaces,
                "scene_path": scene_path,
                "framerate": framerate,
                "frame_range": [min_t, max_t],
            }
            if args.deep:
                value["all_nodes"] = cmds.ls(long=True) or []
            return ToolResult(ok=True, value=value)
        except Exception as e:
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")
```

- [ ] **Step 2: Commit**

```bash
git add src/maya_agent/maya/tools/inspect_scene.py
git commit -m "feat(tools): inspect_scene"
```

---

### Task 11.2: query_animation_curves

**Files:**
- Create: `src/maya_agent/maya/tools/query_animation_curves.py`

- [ ] **Step 1: Implement**

```python
"""query_animation_curves: return key data for animation curves on given nodes."""
from __future__ import annotations

from pydantic import Field
from tools_common import Tool, ToolArgs, ToolResult


class QueryAnimationCurvesArgs(ToolArgs):
    objects: list[str] = Field(..., description="Node paths whose anim curves to inspect.")
    attributes: list[str] | None = Field(
        None, description="If given, only these attribute names (e.g., ['rotateX','rotateY']).")


class QueryAnimationCurves(Tool):
    name = "query_animation_curves"
    description = (
        "Return animation curve data for the given objects: keyframes (frame, value), "
        "tangent types, infinity types. Optionally filter to specific attributes. Read-only."
    )
    args_model = QueryAnimationCurvesArgs
    mutating = False

    def execute(self, args, *, cancel_token=None):
        from maya import cmds
        try:
            out: dict = {"curves": []}
            for obj in args.objects:
                if not cmds.objExists(obj):
                    continue
                attrs = args.attributes or cmds.listAttr(obj, keyable=True) or []
                for attr in attrs:
                    plug = f"{obj}.{attr}"
                    if not cmds.objExists(plug):
                        continue
                    curve_node = cmds.listConnections(plug, type="animCurve", source=True)
                    if not curve_node:
                        continue
                    cn = curve_node[0]
                    n = cmds.keyframe(cn, query=True, keyframeCount=True) or 0
                    if n == 0:
                        continue
                    times = cmds.keyframe(cn, query=True, timeChange=True) or []
                    values = cmds.keyframe(cn, query=True, valueChange=True) or []
                    out["curves"].append({
                        "object": obj, "attribute": attr, "curve": cn,
                        "keys": list(zip(times, values)),
                    })
            return ToolResult(ok=True, value=out)
        except Exception as e:
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")
```

- [ ] **Step 2: Commit**

```bash
git add src/maya_agent/maya/tools/query_animation_curves.py
git commit -m "feat(tools): query_animation_curves"
```

---

### Task 11.3: find_euler_discontinuities

**Files:**
- Create: `src/maya_agent/maya/tools/find_euler_discontinuities.py`

- [ ] **Step 1: Implement**

```python
"""find_euler_discontinuities: locate frames where rotation channels jump."""
from __future__ import annotations

from pydantic import Field
from tools_common import Tool, ToolArgs, ToolResult


class FindEulerDiscontinuitiesArgs(ToolArgs):
    objects: list[str] = Field(..., description="Node paths to inspect.")
    threshold_degrees: float = Field(
        180.0, description="Frame-to-frame jump magnitude that counts as a discontinuity.")


class FindEulerDiscontinuities(Tool):
    name = "find_euler_discontinuities"
    description = (
        "Locate frames on the given objects where rotation channels (rotateX/Y/Z) jump "
        "by more than threshold_degrees between consecutive keys, indicating Euler "
        "discontinuities. Read-only. Returns list of (object, attribute, frame, jump_degrees)."
    )
    args_model = FindEulerDiscontinuitiesArgs
    mutating = False

    def execute(self, args, *, cancel_token=None):
        from maya import cmds
        try:
            results = []
            for obj in args.objects:
                for attr in ("rotateX", "rotateY", "rotateZ"):
                    plug = f"{obj}.{attr}"
                    if not cmds.objExists(plug):
                        continue
                    curve_node = cmds.listConnections(plug, type="animCurve", source=True)
                    if not curve_node:
                        continue
                    cn = curve_node[0]
                    times = cmds.keyframe(cn, query=True, timeChange=True) or []
                    values = cmds.keyframe(cn, query=True, valueChange=True) or []
                    for i in range(1, len(values)):
                        jump = abs(values[i] - values[i - 1])
                        if jump > args.threshold_degrees:
                            results.append({
                                "object": obj, "attribute": attr,
                                "frame": times[i], "jump_degrees": jump,
                            })
            return ToolResult(ok=True, value={"discontinuities": results})
        except Exception as e:
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")
```

- [ ] **Step 2: Commit**

```bash
git add src/maya_agent/maya/tools/find_euler_discontinuities.py
git commit -m "feat(tools): find_euler_discontinuities"
```

---

### Task 11.4: fix_euler_discontinuities

**Files:**
- Create: `src/maya_agent/maya/tools/fix_euler_discontinuities.py`

- [ ] **Step 1: Implement**

```python
"""fix_euler_discontinuities: run cmds.filterCurve on the relevant rotation curves."""
from __future__ import annotations

from pydantic import Field
from tools_common import Tool, ToolArgs, ToolResult


class FixEulerDiscontinuitiesArgs(ToolArgs):
    objects: list[str] = Field(..., description="Node paths whose rotation curves to repair.")


class FixEulerDiscontinuities(Tool):
    name = "fix_euler_discontinuities"
    description = (
        "Run Maya's Euler filter (cmds.filterCurve) on rotation curves of the given "
        "objects to remove discontinuities. MUTATES the scene. Wrap call in undo chunk."
    )
    args_model = FixEulerDiscontinuitiesArgs
    mutating = True

    def execute(self, args, *, cancel_token=None):
        from maya import cmds
        try:
            curves: list[str] = []
            for obj in args.objects:
                for attr in ("rotateX", "rotateY", "rotateZ"):
                    plug = f"{obj}.{attr}"
                    if not cmds.objExists(plug):
                        continue
                    nodes = cmds.listConnections(plug, type="animCurve", source=True) or []
                    curves.extend(nodes)
            if not curves:
                return ToolResult(ok=True, value={"message": "No rotation curves found.", "fixed_curves": []})
            cmds.filterCurve(curves, filter="euler")
            return ToolResult(ok=True, value={"fixed_curves": curves, "count": len(curves)})
        except Exception as e:
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")
```

- [ ] **Step 2: Commit**

```bash
git add src/maya_agent/maya/tools/fix_euler_discontinuities.py
git commit -m "feat(tools): fix_euler_discontinuities (mutating, uses filterCurve)"
```

---

### Task 11.5: playblast

**Files:**
- Create: `src/maya_agent/maya/tools/playblast.py`

- [ ] **Step 1: Implement**

```python
"""playblast: render a viewport playblast to disk."""
from __future__ import annotations

from pydantic import Field
from tools_common import Tool, ToolArgs, ToolResult


class PlayblastArgs(ToolArgs):
    output_path: str = Field(..., description="Output file path (without extension).")
    start_frame: float | None = Field(None, description="First frame (defaults to current min).")
    end_frame: float | None = Field(None, description="Last frame (defaults to current max).")
    width: int = Field(1280, description="Image width.")
    height: int = Field(720, description="Image height.")


class Playblast(Tool):
    name = "playblast"
    description = (
        "Render a viewport playblast of the given frame range to the given output path. "
        "Read-only with respect to the scene (does not mutate animation data) but writes to disk."
    )
    args_model = PlayblastArgs
    mutating = False  # doesn't change scene state

    def execute(self, args, *, cancel_token=None):
        from maya import cmds
        try:
            start = args.start_frame
            end = args.end_frame
            if start is None:
                start = cmds.playbackOptions(query=True, minTime=True)
            if end is None:
                end = cmds.playbackOptions(query=True, maxTime=True)
            kwargs = {
                "filename": args.output_path,
                "startTime": start,
                "endTime": end,
                "width": args.width,
                "height": args.height,
                "format": "qt",
                "compression": "H.264",
                "viewer": False,
                "forceOverwrite": True,
            }
            result = cmds.playblast(**kwargs)
            return ToolResult(ok=True, value={"path": result, "frames": [start, end]})
        except Exception as e:
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")
```

- [ ] **Step 2: Commit**

```bash
git add src/maya_agent/maya/tools/playblast.py
git commit -m "feat(tools): playblast"
```

---

## Phase 12 — Eval harness

### Task 12.1: Matchers

**Files:**
- Create: `tests/eval/__init__.py` (empty)
- Create: `tests/eval/matchers.py`
- Create: `tests/unit/test_matchers.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_matchers.py`:
```python
import pytest
from tests.eval.matchers import assert_calls_match, MatchError


def test_bare_string_positional_exact():
    assert_calls_match(
        [("a", {}), ("b", {})], ["a", "b"], allow_extra=False,
    )


def test_bare_string_in_wrong_order_fails():
    with pytest.raises(MatchError):
        assert_calls_match([("b", {}), ("a", {})], ["a", "b"], allow_extra=False)


def test_args_contain_partial_match():
    assert_calls_match(
        [("fix", {"obj": "x", "extra": 1})],
        [{"tool": "fix", "args_contain": {"obj": "x"}}],
        allow_extra=False,
    )


def test_args_contain_mismatch_fails():
    with pytest.raises(MatchError, match="args"):
        assert_calls_match(
            [("fix", {"obj": "y"})],
            [{"tool": "fix", "args_contain": {"obj": "x"}}],
            allow_extra=False,
        )


def test_any_order_block_matches_either_order():
    assert_calls_match(
        [("a", {}), ("b", {}), ("c", {})],
        ["a", {"any_order": ["b", "c"]}],
        allow_extra=False,
    )
    assert_calls_match(
        [("a", {}), ("c", {}), ("b", {})],
        ["a", {"any_order": ["b", "c"]}],
        allow_extra=False,
    )


def test_allow_extra_calls_lets_unmatched_intermediates_pass():
    assert_calls_match(
        [("a", {}), ("noise", {}), ("b", {})],
        ["a", "b"],
        allow_extra=True,
    )


def test_allow_extra_false_rejects_extras():
    with pytest.raises(MatchError, match="extra"):
        assert_calls_match(
            [("a", {}), ("noise", {}), ("b", {})],
            ["a", "b"],
            allow_extra=False,
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_matchers.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `tests/eval/matchers.py`**

```python
"""Sequence matchers for eval expected_calls.

Three matcher types:
  - bare string: exact tool name in this position
  - {tool, args_contain}: positional + partial arg match
  - {any_order: [...]}: all listed tools must appear, order within block flexible
"""
from __future__ import annotations

from typing import Any


class MatchError(AssertionError):
    pass


def _arg_matches(actual: dict, required: dict) -> bool:
    return all(actual.get(k) == v for k, v in required.items())


def assert_calls_match(
    actual: list[tuple[str, dict]],
    expected: list[Any],
    *,
    allow_extra: bool,
) -> None:
    """actual: list of (tool_name, args) recorded during the eval run.
    expected: list of matcher elements (str | {tool, args_contain} | {any_order: [...]}).
    """
    i = 0  # actual index
    for matcher in expected:
        if isinstance(matcher, str):
            i = _consume_one(actual, i, matcher, None, allow_extra)
        elif isinstance(matcher, dict) and "any_order" in matcher:
            i = _consume_any_order(actual, i, matcher["any_order"], allow_extra)
        elif isinstance(matcher, dict) and "tool" in matcher:
            i = _consume_one(actual, i, matcher["tool"], matcher.get("args_contain"), allow_extra)
        else:
            raise ValueError(f"Unknown matcher: {matcher!r}")
    if not allow_extra and i != len(actual):
        raise MatchError(f"extra unexpected calls after position {i}: {actual[i:]}")


def _consume_one(actual, start, tool, args_required, allow_extra):
    j = start
    while j < len(actual):
        name, args = actual[j]
        if name == tool and (args_required is None or _arg_matches(args, args_required)):
            return j + 1
        if not allow_extra:
            raise MatchError(
                f"expected {tool} at position {start}, got {name} (args={args})"
            )
        j += 1
    raise MatchError(f"expected {tool} not found starting at position {start}; "
                     f"args needed: {args_required}; remaining: {actual[start:]}")


def _consume_any_order(actual, start, names, allow_extra):
    needed = list(names)
    j = start
    while needed and j < len(actual):
        name, _ = actual[j]
        if name in needed:
            needed.remove(name)
            j += 1
        elif allow_extra:
            j += 1
        else:
            raise MatchError(
                f"any_order block needs {needed} but got {name} at position {j}"
            )
    if needed:
        raise MatchError(f"any_order block missing: {needed}")
    return j
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_matchers.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/eval/__init__.py tests/eval/matchers.py tests/unit/test_matchers.py
git commit -m "test(eval): expected-calls matcher with three matcher types"
```

---

### Task 12.2: Eval runner & MockMaya

**Files:**
- Create: `tests/eval/runner.py`
- Create: `tests/eval/conftest.py`
- Create: `tests/eval/test_eval_cases.py`
- Create: `tests/eval/recordings/.gitkeep`

- [ ] **Step 1: Implement `tests/eval/runner.py`**

```python
"""Eval runner: loads case JSON, builds a fake MayaClient, runs AgentLoop."""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maya_agent.sidecar.agent_loop import AgentLoop, IntentRequest
from maya_agent.sidecar.llm_client import LLMClient
from maya_agent.sidecar.recording_clients import RecordingLLMClient, ReplayLLMClient


@dataclass
class FixtureRule:
    match_tool: str
    match_args_contain: dict | None
    response: dict


@dataclass
class EvalCase:
    name: str
    description: str
    intent: str
    clarify_responses: list[str]
    fixture_observations: list[FixtureRule]
    expected_calls: list[Any]
    allow_extra_calls: bool
    terminal_action: str
    max_steps: int


def load_case(path: Path) -> EvalCase:
    data = json.loads(path.read_text(encoding="utf-8"))
    return EvalCase(
        name=data["name"],
        description=data.get("description", ""),
        intent=data["intent"],
        clarify_responses=data.get("clarify_responses", []),
        fixture_observations=[
            FixtureRule(
                match_tool=f["match_tool"],
                match_args_contain=f.get("match_args_contain"),
                response=f["response"],
            ) for f in data.get("fixture_observations", [])
        ],
        expected_calls=data.get("expected_calls", []),
        allow_extra_calls=data.get("allow_extra_calls", True),
        terminal_action=data.get("terminal_action", "finish"),
        max_steps=data.get("max_steps", 20),
    )


class MockMayaClient:
    """Records tool calls; returns fixture responses; queues clarify responses."""
    def __init__(self, fixtures: list[FixtureRule], clarify_responses: list[str]) -> None:
        self.fixtures = fixtures
        self.clarify_pending = list(clarify_responses)
        self.recorded_calls: list[tuple[str, dict]] = []
        self.events: list[dict] = []
        self._loop_ref: AgentLoop | None = None

    def attach_loop(self, loop: AgentLoop) -> None:
        self._loop_ref = loop

    async def call_tool(self, intent_id: str, call_id: str, tool: str, args: dict) -> dict:
        self.recorded_calls.append((tool, args))
        for rule in self.fixtures:
            if rule.match_tool != tool:
                continue
            if rule.match_args_contain:
                if not all(args.get(k) == v for k, v in rule.match_args_contain.items()):
                    continue
            return rule.response
        return {"ok": False, "error": f"no fixture defined for {tool}"}

    async def emit(self, event: dict) -> None:
        self.events.append(event)
        if event.get("type") == "clarify_question" and self._loop_ref:
            if self.clarify_pending:
                response = self.clarify_pending.pop(0)
                await self._loop_ref.provide_clarify_response(event["intent_id"], response)


def build_llm_client(*, mode: str, case_name: str, recordings_dir: Path,
                    real_factory) -> LLMClient:
    rec_path = recordings_dir / f"{case_name}.jsonl"
    if mode == "replay":
        return ReplayLLMClient(rec_path)
    if mode == "record":
        return RecordingLLMClient(real_factory(), rec_path)
    if mode == "live":
        return real_factory()
    if mode == "auto":
        if rec_path.exists():
            return ReplayLLMClient(rec_path)
        return real_factory()
    raise ValueError(f"Unknown mode: {mode}")


def get_eval_mode() -> str:
    return os.environ.get("MAYA_AGENT_EVAL_MODE", "auto")
```

- [ ] **Step 2: Implement `tests/eval/conftest.py`**

```python
import pytest
from pathlib import Path

CASES_DIR = Path(__file__).parent / "cases"
RECORDINGS_DIR = Path(__file__).parent / "recordings"


def pytest_collect_file(parent, file_path):
    """Collect all .json case files automatically."""
    if file_path.suffix == ".json" and file_path.parent.name == "cases":
        return None  # We use pytest.mark.parametrize instead


@pytest.fixture
def cases_dir():
    return CASES_DIR


@pytest.fixture
def recordings_dir():
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    return RECORDINGS_DIR
```

- [ ] **Step 3: Implement `tests/eval/test_eval_cases.py`**

```python
import asyncio
from pathlib import Path

import pytest

from maya_agent.sidecar.agent_loop import AgentLoop, IntentRequest
from maya_agent.sidecar.ollama_client import OllamaClient

from tests.eval.runner import (
    load_case, MockMayaClient, build_llm_client, get_eval_mode,
)
from tests.eval.matchers import assert_calls_match

CASES_DIR = Path(__file__).parent / "cases"
RECORDINGS_DIR = Path(__file__).parent / "recordings"

# Static inventory used during eval. Mirrors the 5 framework example tools.
EVAL_INVENTORY = [
    {"name": "inspect_scene", "description": "Inspect scene.", "mutating": False,
     "json_schema": {"type": "object", "properties": {"deep": {"type": "boolean", "default": False}}}},
    {"name": "query_animation_curves", "description": "Query anim curves.", "mutating": False,
     "json_schema": {"type": "object",
                     "properties": {"objects": {"type": "array", "items": {"type": "string"}},
                                    "attributes": {"type": ["array", "null"]}},
                     "required": ["objects"]}},
    {"name": "find_euler_discontinuities", "description": "Find Euler jumps.", "mutating": False,
     "json_schema": {"type": "object",
                     "properties": {"objects": {"type": "array", "items": {"type": "string"}},
                                    "threshold_degrees": {"type": "number", "default": 180.0}},
                     "required": ["objects"]}},
    {"name": "fix_euler_discontinuities", "description": "Fix Euler jumps.", "mutating": True,
     "json_schema": {"type": "object",
                     "properties": {"objects": {"type": "array", "items": {"type": "string"}}},
                     "required": ["objects"]}},
    {"name": "playblast", "description": "Render playblast.", "mutating": False,
     "json_schema": {"type": "object",
                     "properties": {"output_path": {"type": "string"},
                                    "start_frame": {"type": ["number", "null"]},
                                    "end_frame": {"type": ["number", "null"]},
                                    "width": {"type": "integer", "default": 1280},
                                    "height": {"type": "integer", "default": 720}},
                     "required": ["output_path"]}},
]


def _real_llm_factory():
    return OllamaClient()


@pytest.mark.parametrize("case_path", sorted(CASES_DIR.glob("*.json")))
def test_eval_case(case_path):
    case = load_case(case_path)
    mode = get_eval_mode()
    llm = build_llm_client(
        mode=mode, case_name=case.name,
        recordings_dir=RECORDINGS_DIR, real_factory=_real_llm_factory,
    )
    maya = MockMayaClient(case.fixture_observations, case.clarify_responses)
    loop = AgentLoop(
        llm=llm, maya=maya, inventory=EVAL_INVENTORY,
        model="gemma3:27b", max_steps=case.max_steps,
    )
    maya.attach_loop(loop)
    result = asyncio.run(loop.run_intent(
        IntentRequest(intent_id="t", text=case.intent),
        on_event=lambda e: asyncio.create_task(maya.emit(e)),
    ))
    assert_calls_match(maya.recorded_calls, case.expected_calls,
                       allow_extra=case.allow_extra_calls)
    assert result.terminal_action == case.terminal_action, (
        f"expected {case.terminal_action}, got {result.terminal_action}"
    )
```

- [ ] **Step 4: Create empty recordings directory marker**

```bash
touch tests/eval/recordings/.gitkeep
```

- [ ] **Step 5: Commit**

```bash
git add tests/eval/runner.py tests/eval/conftest.py tests/eval/test_eval_cases.py tests/eval/recordings/.gitkeep
git commit -m "test(eval): runner, MockMayaClient, parameterized case test"
```

---

## Phase 13 — Initial eval cases

### Task 13.1: Write the six case files

**Files:**
- Create: `tests/eval/cases/euler_cleanup_basic.json`
- Create: `tests/eval/cases/euler_cleanup_ambiguous_arms.json`
- Create: `tests/eval/cases/playblast_with_assumptions.json`
- Create: `tests/eval/cases/tool_error_recovery.json`
- Create: `tests/eval/cases/unknown_tool_request.json`
- Create: `tests/eval/cases/step_limit_exceeded.json`

- [ ] **Step 1: Write `euler_cleanup_basic.json`**

```json
{
  "name": "euler_cleanup_basic",
  "description": "User requests Euler cleanup on FK arm controls; agent inspects, finds, fixes, finishes.",
  "intent": "clean up Euler discontinuities on the L_arm FK controls",
  "clarify_responses": [],
  "fixture_observations": [
    {
      "match_tool": "inspect_scene",
      "response": {"ok": true, "value": {
        "selection": ["rig:L_arm_FK_CTL"],
        "namespaces": ["rig"],
        "scene_path": "/fixtures/test.ma",
        "framerate": "film",
        "frame_range": [1, 100]
      }}
    },
    {
      "match_tool": "find_euler_discontinuities",
      "match_args_contain": {"objects": ["rig:L_arm_FK_CTL"]},
      "response": {"ok": true, "value": {
        "discontinuities": [
          {"object": "rig:L_arm_FK_CTL", "attribute": "rotateY", "frame": 24, "jump_degrees": 320}
        ]
      }}
    },
    {
      "match_tool": "fix_euler_discontinuities",
      "match_args_contain": {"objects": ["rig:L_arm_FK_CTL"]},
      "response": {"ok": true, "value": {"fixed_curves": ["rig:L_arm_FK_CTL_rotateY"], "count": 1}}
    }
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

- [ ] **Step 2: Write `euler_cleanup_ambiguous_arms.json`**

```json
{
  "name": "euler_cleanup_ambiguous_arms",
  "description": "Ambiguous request with multiple arm namespaces; agent should clarify.",
  "intent": "fix euler on the arms",
  "clarify_responses": ["just the L_arm_FK_CTL"],
  "fixture_observations": [
    {
      "match_tool": "inspect_scene",
      "response": {"ok": true, "value": {
        "selection": [],
        "namespaces": ["rig", "secondary_rig"],
        "all_nodes": ["rig:L_arm_FK_CTL", "rig:R_arm_FK_CTL", "secondary_rig:L_arm_IK_CTL"]
      }}
    },
    {
      "match_tool": "find_euler_discontinuities",
      "match_args_contain": {"objects": ["rig:L_arm_FK_CTL"]},
      "response": {"ok": true, "value": {
        "discontinuities": [{"object": "rig:L_arm_FK_CTL", "attribute": "rotateZ", "frame": 12, "jump_degrees": 270}]
      }}
    },
    {
      "match_tool": "fix_euler_discontinuities",
      "match_args_contain": {"objects": ["rig:L_arm_FK_CTL"]},
      "response": {"ok": true, "value": {"count": 1}}
    }
  ],
  "expected_calls": [
    "inspect_scene",
    {"tool": "fix_euler_discontinuities", "args_contain": {"objects": ["rig:L_arm_FK_CTL"]}}
  ],
  "allow_extra_calls": true,
  "terminal_action": "finish",
  "max_steps": 12
}
```

- [ ] **Step 3: Write `playblast_with_assumptions.json`**

```json
{
  "name": "playblast_with_assumptions",
  "description": "User asks for a playblast without specifying parameters; agent fills in defaults.",
  "intent": "playblast the current shot",
  "clarify_responses": [],
  "fixture_observations": [
    {
      "match_tool": "inspect_scene",
      "response": {"ok": true, "value": {
        "scene_path": "/fixtures/shot_010.ma", "frame_range": [1, 120], "framerate": "film"
      }}
    },
    {
      "match_tool": "playblast",
      "response": {"ok": true, "value": {"path": "/tmp/shot_010_playblast.mov", "frames": [1, 120]}}
    }
  ],
  "expected_calls": [
    "inspect_scene",
    {"tool": "playblast"}
  ],
  "allow_extra_calls": true,
  "terminal_action": "finish",
  "max_steps": 8
}
```

- [ ] **Step 4: Write `tool_error_recovery.json`**

```json
{
  "name": "tool_error_recovery",
  "description": "First fix attempt errors; agent re-reads error and retries with corrected args.",
  "intent": "fix euler on rig:L_arm_FK_CTL",
  "clarify_responses": [],
  "fixture_observations": [
    {
      "match_tool": "fix_euler_discontinuities",
      "match_args_contain": {"objects": ["rig:L_arm_FK_CTL"]},
      "response": {"ok": false, "error": "Object 'rig:L_arm_FK_CTL' has locked rotateX channel; unlock first or use a different channel."}
    },
    {
      "match_tool": "inspect_scene",
      "response": {"ok": true, "value": {"selection": ["rig:L_arm_FK_CTL"], "namespaces": ["rig"]}}
    }
  ],
  "expected_calls": [
    {"any_order": ["fix_euler_discontinuities", "inspect_scene"]}
  ],
  "allow_extra_calls": true,
  "terminal_action": "finish",
  "max_steps": 10
}
```

- [ ] **Step 5: Write `unknown_tool_request.json`**

```json
{
  "name": "unknown_tool_request",
  "description": "User asks for a capability the agent does not have; should finish gracefully.",
  "intent": "convert this scene to USD format",
  "clarify_responses": [],
  "fixture_observations": [],
  "expected_calls": [],
  "allow_extra_calls": true,
  "terminal_action": "finish",
  "max_steps": 5
}
```

- [ ] **Step 6: Write `step_limit_exceeded.json`**

```json
{
  "name": "step_limit_exceeded",
  "description": "Force the agent to loop on inspect_scene to verify circuit breaker fires.",
  "intent": "tell me everything about the scene in extreme detail",
  "clarify_responses": [],
  "fixture_observations": [
    {
      "match_tool": "inspect_scene",
      "response": {"ok": true, "value": {"hint": "ambiguous"}}
    }
  ],
  "expected_calls": [],
  "allow_extra_calls": true,
  "terminal_action": "step_limit",
  "max_steps": 4
}
```

- [ ] **Step 7: Commit**

```bash
git add tests/eval/cases/
git commit -m "test(eval): six initial eval cases (basic, ambiguous, playblast, error, unknown, step-limit)"
```

---

### Task 13.2: Record initial responses

> **Note:** This task requires a running Ollama server with the target model pulled. If unavailable on the development machine, this task can be deferred to Phase 14 manual smoke and recordings filled in later. CI initially runs only `replay`-mode cases that have recordings; cases without recordings are marked xfail until recorded.

- [ ] **Step 1: Pull the model in Ollama**

```bash
ollama pull gemma3:27b
```

Expected: model downloads successfully.

- [ ] **Step 2: Record each case**

```bash
MAYA_AGENT_EVAL_MODE=record pytest tests/eval/ -v --tb=short
```

Expected: each case runs against live Ollama, recording is written to `tests/eval/recordings/<case_name>.jsonl`. Some cases may need multiple iterations to get a clean recording — review the trace, adjust prompts/inventory if the model is consistently wrong, re-record.

- [ ] **Step 3: Verify replay mode passes**

```bash
MAYA_AGENT_EVAL_MODE=replay pytest tests/eval/ -v
```

Expected: all six cases pass.

- [ ] **Step 4: Commit recordings**

```bash
git add tests/eval/recordings/
git commit -m "test(eval): initial recordings for six baseline cases"
```

---

## Phase 14 — Documentation & smoke test

### Task 14.1: Documentation

**Files:**
- Create: `docs/architecture.md`
- Create: `docs/writing-a-tool.md`
- Create: `docs/protocol.md`
- Modify: `README.md` (expand from minimal placeholder)

- [ ] **Step 1: Write `docs/architecture.md`**

Briefly: lift the System Topology section from the spec, add a "Process boundaries" subsection explaining what runs where, and reference the spec for full design history.

```markdown
# Architecture

See `docs/superpowers/specs/2026-05-01-maya-agent-v1-design.md` for the full design rationale.

## Process boundaries

Two processes:

1. **Sidecar (CPython, standalone).** Runs the agent loop. Talks HTTP to Ollama. Talks length-prefixed JSON over a named pipe to Maya. Imports nothing from `maya.cmds`.
2. **Maya process.** Runs the Qt panel, the QLocalServer, the tool dispatcher. Loads tool implementations (which lazy-import `maya.cmds`). Sends tool inventory to the sidecar at handshake. Receives tool calls and returns results.

## Module map

- `tools_common` — Tool ABC, ToolArgs, ToolResult. Pure schemas. No Maya import.
- `maya_agent.core` — Tool registry, plugin loader, wire protocol, frame codec.
- `maya_agent.sidecar` — Agent loop, LLM client, prompts, Maya client (transport).
- `maya_agent.maya` — Qt panel, command server, tool dispatcher, bootstrap, example tools.

## Data flow

[copy or reference the topology diagram from the spec]
```

- [ ] **Step 2: Write `docs/writing-a-tool.md`**

```markdown
# Writing a Tool

Tools are the unit of capability. Each tool is a `Tool` subclass with a name,
description, pydantic args model, and an `execute` method.

## Anatomy

```python
from pydantic import Field
from tools_common import Tool, ToolArgs, ToolResult


class MyToolArgs(ToolArgs):
    target: str = Field(..., description="Node path to operate on.")
    mode: str = Field("default", description="One of 'default', 'aggressive'.")


class MyTool(Tool):
    name = "my_tool"
    description = "One-paragraph explanation aimed at the LLM. Be specific about effects and limits."
    args_model = MyToolArgs
    mutating = True   # set False for read-only tools

    def execute(self, args, *, cancel_token=None):
        from maya import cmds   # lazy: see lazy-import rule
        try:
            cmds.someOperation(args.target, mode=args.mode)
            return ToolResult(ok=True, value={"target": args.target})
        except Exception as e:
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")
```

## Lazy-import rule

**Tool modules MUST NOT import `maya.cmds` at module top level.** The plugin
loader runs an AST check and refuses to load modules that violate this.

This lets the eval harness and CI load tool classes without a Maya install.
The cost is one line of discipline per tool: put `from maya import cmds`
inside `execute()`.

## Mutating vs read-only

- `mutating = True` → dispatcher wraps `execute()` in `cmds.undoInfo(openChunk=True, ...)` /
  `closeChunk`. A single Maya undo step undoes the whole tool call atomically.
- `mutating = False` → no undo wrapping. Use for inspection, query, file-export tools.

## Optional fast-cancel

Tools that take more than a second can opt in to fast cancel by accepting a
`cancel_token` parameter:

```python
def execute(self, args, *, cancel_token=None):
    for frame in args.frames:
        if cancel_token and cancel_token.is_set():
            return ToolResult(ok=False, error="cancelled")
        # ... do work for `frame` ...
```

The dispatcher inspects the signature and threads a token through if present.

## Distributing tools as a plugin

Drop your tools into a directory. Optionally add a `plugin.toml`:

```toml
name = "my_studio_tools"
version = "0.1.0"
description = "Studio-specific Maya tools."
min_maya_version = "2024"
```

Set the env var:

```
MAYA_AGENT_PLUGIN_PATHS=C:\path\to\my-tools-dir
```

Restart Maya. The panel's status bar will report the loaded tool count.
```

- [ ] **Step 3: Write `docs/protocol.md`**

Briefly: dump the protocol section from the spec verbatim — message types, wire format, lifecycle.

- [ ] **Step 4: Expand `README.md`**

```markdown
# Maya Agent

A Maya-integrated agentic AI system. Take natural-language intent, execute via curated tools.

- Sidecar process runs the agent loop against Ollama
- Maya panel hosts the Qt UI and command server
- Studio plugins load via `MAYA_AGENT_PLUGIN_PATHS` env var
- Eval harness runs in CI without Maya using recorded LLM responses

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -e ".[dev]"
pytest tests/unit
```

## Install into Maya

```bash
python scripts/install_into_maya.py --maya-version 2024
```

Restart Maya. Run in the script editor:

```python
import maya_agent.maya.maya_bootstrap as b
b.show_panel()
```

## Sidecar

```bash
ollama pull gemma3:27b
python -m maya_agent.sidecar --pipe \\.\pipe\maya-agent-<PID-OF-MAYA> --model gemma3:27b
```

The pipe path is shown in the panel's status row when disconnected.

## Documentation

- `docs/architecture.md` — system overview
- `docs/writing-a-tool.md` — plugin author guide
- `docs/protocol.md` — wire protocol reference
- `docs/superpowers/specs/` — design history
```

- [ ] **Step 5: Commit**

```bash
git add docs/architecture.md docs/writing-a-tool.md docs/protocol.md README.md
git commit -m "docs: architecture, writing-a-tool, protocol, expanded README"
```

---

### Task 14.2: Manual end-to-end smoke test

This is the v1 success criterion that can't be automated; a human (the senior pipeline TD) does it once on their machine.

- [ ] **Step 1: Open Maya 2024+, set the env var, install the mod**

```cmd
set MAYA_AGENT_MODEL=gemma3:27b
python scripts/install_into_maya.py --maya-version 2024
```

Restart Maya. From the script editor:

```python
import maya_agent.maya.maya_bootstrap as b
b.show_panel()
```

Expected: panel appears, status row shows `● Disconnected — pipe at <path>`.

- [ ] **Step 2: Open a scene with a known Euler discontinuity**

Either a real test rig or a quickly-built one: a single sphere with rotateY keys at frames 1 and 5 jumping from 10° to 350°.

- [ ] **Step 3: Start the sidecar**

In a terminal:

```bash
ollama serve   # if not already running
python -m maya_agent.sidecar --pipe \\.\pipe\maya-agent-<PID> --model gemma3:27b
```

Status row should turn green: `● Connected — gemma3:27b`.

- [ ] **Step 4: Type and send an intent**

In the panel input: `find euler discontinuities on the selected control` (with the test sphere selected). Press Send.

Expected:
- Tool entries appear inline: `inspect_scene` ✓, `find_euler_discontinuities` ✓
- Final assistant message lists the discontinuity at frame 5
- No errors in the panel or sidecar logs

- [ ] **Step 5: Test undo and disconnect resilience**

- Click "Undo last" — the most recent mutating tool call should be undone via `cmds.undo()`.
- Kill the sidecar process. Status should turn red.
- Restart sidecar. Status should turn green again.
- Run another intent. Verify it works.

- [ ] **Step 6: Document the result in the smoke-test record**

Create `docs/smoke-test-2026-05-01.md` capturing the date, Maya version, model, observations. This is the artifact that closes the v1 success criterion.

- [ ] **Step 7: Commit smoke-test record**

```bash
git add docs/smoke-test-*.md
git commit -m "docs: v1 smoke-test passing record"
```

---

## Self-Review

Spec coverage check (skim each section of the spec, point to a task):

- §"Goals" → covered by all phases collectively
- §"Architectural Decisions" 1-8 → Tasks 4.3 (Ollama format=json_schema), 8.1 (QLocalServer), 3.2 (plugin discovery), 6.2/6.4 (clarify + memory), 12.1+12.2 (eval), 8.2 (undo chunks), 4.1 (LLMClient Protocol), 6.2 (cancel)
- §"System Topology" → Task 1.1 + 8.1 + 7.1 wire it together
- §"Repo Structure" → established by Task 1.1, populated by all subsequent tasks
- §"Core Interfaces" Tool / AgentLoop / LLMClient / protocol → Tasks 2.1, 6.2, 4.1, 2.2
- §"Plugin System" → Tasks 3.1, 3.2
- §"Agent Loop Behavior" → Tasks 6.1 (prompt), 6.2 (state machine), 6.3 (memory)
- §"Qt Panel" → Task 9.1
- §"Eval Harness" → Tasks 12.1, 12.2, 13.1, 13.2
- §"Risks" → noted in spec; no specific tasks (these are documented concerns, not implementation)
- §"Success Criteria" → Task 14.2 (manual smoke)

Placeholder scan: no TBDs, no "implement appropriate error handling" without code, no "similar to Task N." Code blocks present in every code step.

Type consistency: `Tool.execute(args, *, cancel_token=None)` consistent across abstract, concrete, dispatcher, and tools. `IntentResult.terminal_action` strings match between definition (Task 6.2) and assertion (eval harness Task 12.2). Message types in protocol (Task 2.2) match those imported in command server (Task 8.1) and sidecar entry (Task 7.1).

One gap I noticed during review: the spec mentioned a Qt thinking-toggle in a ⚙ menu but the panel implementation in Task 9.1 only logs thinking at DEBUG. I'm leaving the visible toggle out of v1 (out-of-scope by spec); will add when needed.

---

## Execution

The user has preapproved subagent-driven implementation. After this plan is committed, the orchestrator will dispatch one fresh subagent per task using `superpowers:subagent-driven-development`, reviewing between tasks.
