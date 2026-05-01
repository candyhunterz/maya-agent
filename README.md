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
# source .venv/bin/activate       # Linux
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
