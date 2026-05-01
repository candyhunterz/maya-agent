# Maya Agent

Natural-language agentic AI for Autodesk Maya. The artist types an intent in a Qt panel; a sidecar process drives a local LLM (Ollama) to call curated Maya tools through a length-prefixed JSON socket. A single `Ctrl+Z` reverts the entire agentic action.

## Status

v1 implementation complete on `feature/v1-implementation`. Unit suite green (56/56). Eval harness green for the scripted recovery case, six cases pending Ollama recordings. Manual smoke test in Maya is the remaining gate before merge.

See `docs/glass-summary.md` for the full implementation report and `docs/smoke-test-instructions.md` for the smoke procedure.

## What it does

Maya Agent is a two-process system:

- **Sidecar** (standalone CPython, no `maya.cmds` import) hosts the agent loop. It speaks HTTP to a local Ollama instance for the LLM and length-prefixed JSON over a named pipe / unix domain socket / TCP loopback to Maya.
- **Maya panel** (PySide6 inside `mayapy`) hosts a chat UI, a `QLocalServer` command server, and a tool dispatcher that lazy-imports `maya.cmds`. Tools live in regular Python files and are discovered through `MAYA_AGENT_PLUGIN_PATHS`.

The LLM never touches `maya.cmds` directly. It selects a tool, the dispatcher validates arguments against the tool's schema, and a per-intent outer undo chunk wraps every tool call so the artist can undo the agent the same way they undo any other action.

## Architecture

```
User intent (Qt panel)
        |
        v
  CommandServer  <-- length-prefixed JSON / Auth handshake -->  Sidecar
        |                                                            |
        |                                                            v
        |                                                     AgentLoop
        |                                                            |
        |                                          +-----------------+----------------+
        |                                          v                                   v
        |                                   Ollama (LLM)                     ToolCallMessage
        |                                                                              |
        v                                                                              v
  ToolDispatcher (validate args, open undo chunk, dispatch) -- ToolResultMessage --> sidecar
```

Full design rationale in `docs/superpowers/specs/2026-05-01-maya-agent-v1-design.md`. Wire-protocol reference in `docs/protocol.md`.

## Requirements

- Python 3.10+
- Maya 2024+ (panel + tool execution; not needed for unit tests)
- Ollama with `gemma3:27b` pulled (recording mode + live use; replay mode does not need it)
- Linux is the studio production target; Windows is supported as a development environment via TCP-loopback transport.

## Quick start

### Sidecar (development, no Maya needed)

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # Linux / macOS
pip install -e ".[dev]"
pytest tests/unit                 # 56 tests
```

### Install into Maya

```bash
python scripts/install_into_maya.py --maya-version 2024
```

Restart Maya, then in the script editor:

```python
import maya_agent.maya.maya_bootstrap as b
b.show_panel()
```

### Launch the sidecar

```bash
ollama pull gemma3:27b
python -m maya_agent.sidecar \
    --pipe \\.\pipe\maya-agent-<MAYA_PID> \
    --model gemma3:27b
```

The pipe path is shown in the panel's status row when disconnected. On Linux, the pipe path is a unix domain socket under `~/.maya-agent/`.

## Repository layout

```
src/
  tools_common/               Tool ABC, ToolArgs, ToolResult (no Maya import)
  maya_agent/
    core/                     Tool registry, plugin loader, wire protocol, frame codec
    sidecar/                  Agent loop, LLM client, prompts, MayaClient transport
    maya/                     Qt panel, CommandServer, ToolDispatcher, bootstrap
      tools/                  Five example tools (inspect_scene, playblast, etc.)
tests/
  unit/                       56 unit tests (no Maya, no Ollama)
  eval/                       Recording/replay harness, 7 cases
docs/                         Architecture, protocol, plugin-author guide
scripts/                      install_into_maya.py
```

## Testing

```bash
pytest tests/unit -q          # always runnable
pytest tests/eval -q          # replay mode by default; skips cleanly without recordings

# Re-record eval responses (requires Ollama + gemma3:27b)
MAYA_AGENT_EVAL_MODE=record pytest tests/eval/
```

The eval harness records LLM responses to JSONL on first run and replays them on subsequent runs, so CI does not depend on a live Ollama. See `docs/superpowers/specs/2026-05-01-maya-agent-v1-design.md` for why this beats a mocked LLM.

## Writing a tool

Plugins are plain Python files. See `docs/writing-a-tool.md` for the full guide. A tool subclasses `Tool`, declares a `ToolArgs` schema, and returns a `ToolResult`. Mutating tools opt into per-tool undo chunks by setting `mutating = True` on the class.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — system overview, process boundaries, auth handshake
- [`docs/protocol.md`](docs/protocol.md) — wire protocol, frame format, message types
- [`docs/writing-a-tool.md`](docs/writing-a-tool.md) — plugin author guide
- [`docs/glass-summary.md`](docs/glass-summary.md) — v1 implementation report
- [`docs/smoke-test-instructions.md`](docs/smoke-test-instructions.md) — manual smoke procedure
- `docs/superpowers/specs/2026-05-01-maya-agent-v1-design.md` — full design document
- `docs/superpowers/plans/2026-05-01-maya-agent-v1-implementation.md` — 14-phase implementation plan
