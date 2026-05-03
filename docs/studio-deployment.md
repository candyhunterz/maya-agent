# Studio Deployment (Air-Gapped)

Step-by-step setup for an air-gapped Linux studio with Maya 2024+ and SPK-managed Ollama. Everything that needs the internet happens on the connected dev box; the studio host only consumes the resulting bundle.

## What's on the studio host

Verified at the studio via `python scripts/check-studio-env.py`:

| | Status | Notes |
|---|---|---|
| Maya 2024 mayapy | present, Python 3.10.8 | at `/spfs/opt/maya/bin/mayapy` |
| Qt binding in mayapy | PySide2 5.15.2 | bundled with Maya 2024 |
| Host Python | 3.9 (too old) | use mayapy's 3.10 instead |
| pip in mayapy | yes | `mayapy -m pip` |
| Ollama | wrapped in SPK | `spk env ollama` then `ollama-ctl start-server` |
| `httpx`, `pydantic`, `qtpy` wheels | not installed | ship via USB |
| `gemma4:31b` model | depends on Ollama state | check with `ollama list` once server is up |

## Phase 1 — On a connected (dev) machine

### 1.1 Stage the Python wheels

```bash
mkdir -p ./maya-agent-studio-wheels
pip download httpx pydantic qtpy \
  --python-version 3.10 \
  --platform manylinux2014_x86_64 \
  --only-binary=:all: \
  -d ./maya-agent-studio-wheels
```

This produces ~13 wheels, ~3.3 MB total. Includes `pydantic_core` (the only Linux-specific wheel), plus pure-Python deps (`httpx`, `httpcore`, `h11`, `anyio`, `idna`, `certifi`, `pydantic`, `annotated_types`, `typing_extensions`, `typing_inspection`, `packaging`, `qtpy`).

Zip it:

```bash
zip -r maya-agent-studio-wheels.zip maya-agent-studio-wheels/
```

### 1.2 Stage the model files (~18 GB)

```bash
ollama pull gemma4:31b
```

The model lives at `~/.ollama/models/`. Tar that directory:

```bash
tar -czf ollama-models-gemma4-31b.tar.gz -C ~/.ollama models
```

### 1.3 Stage the source

Either:

```bash
git clone https://github.com/candyhunterz/maya-agent.git
zip -r maya-agent-source.zip maya-agent/
```

Or with `git bundle` if the studio uses git internally:

```bash
git -C maya-agent bundle create maya-agent.bundle --all
```

### 1.4 Cross to the studio

Carry over: `maya-agent-studio-wheels.zip`, `ollama-models-gemma4-31b.tar.gz`, and `maya-agent-source.zip` (or `.bundle`).

## Phase 2 — On the studio host

### 2.1 Unpack source

```bash
cd ~
unzip maya-agent-source.zip
cd maya-agent
```

If using a bundle: `git clone maya-agent.bundle maya-agent && cd maya-agent`.

### 2.2 Run the doctor (pre-install baseline)

```bash
python scripts/check-studio-env.py
```

Expect failures for `httpx`, `pydantic`, and `Ollama binary` (the latter because Ollama is gated behind SPK — see 2.4). Maya should be green.

### 2.3 Install Python deps into mayapy

```bash
unzip ../maya-agent-studio-wheels.zip
/spfs/opt/maya/bin/mayapy -m pip install \
  --no-index \
  --find-links=./maya-agent-studio-wheels \
  httpx pydantic qtpy
```

Verify:

```bash
/spfs/opt/maya/bin/mayapy -c "import httpx, pydantic, qtpy; print(httpx.__version__, pydantic.VERSION, qtpy.__version__)"
```

### 2.4 Stage the Ollama model

If `gemma4:31b` is not already present:

```bash
mkdir -p ~/.ollama
tar -xzf ../ollama-models-gemma4-31b.tar.gz -C ~/.ollama
```

### 2.5 Start the Ollama server

```bash
spk env ollama
ollama-ctl start-server
ollama list   # verify gemma4:31b is listed
exit          # leave the spk env; the server keeps running
```

The server now listens on `http://localhost:11434`. The sidecar will reach it directly without needing the SPK env active.

### 2.6 Sanity-check via the doctor

```bash
python scripts/check-studio-env.py
```

You'll still see `Ollama binary not on PATH` (because it's wrapped in SPK), but the server probe at `http://localhost:11434` should be green and the doctor should list `gemma4:31b` as pulled. The host-Python failures are also still red — that's expected; we use mayapy instead.

## Phase 3 — Run

### 3.1 Install the Maya module

```bash
export MAYA_AGENT_MODEL=gemma4:31b
/spfs/opt/maya/bin/mayapy scripts/install_into_maya.py --maya-version 2024
```

Restart Maya.

### 3.2 Open the panel

In Maya's Python script editor:

```python
import maya_agent.maya.maya_bootstrap as b
b.show_panel()
```

The panel should appear with status `● Disconnected — pipe at <path>`.

### 3.3 Start the sidecar

In a separate terminal:

```bash
/spfs/opt/maya/bin/mayapy -m maya_agent.sidecar \
  --pipe /tmp/maya-agent-<MAYA_PID>.sock \
  --session-token-file ~/.maya-agent/session-<MAYA_PID>.token \
  --model gemma4:31b \
  --ollama-base-url http://localhost:11434
```

The pipe path and token-file path appear in the panel's status row; copy them from there.

The panel status should turn green: `● Connected — sending inventory`.

### 3.4 Smoke test

Follow `docs/smoke-test-instructions.md`. Capture the result in `docs/smoke-test-<YYYY-MM-DD>.md` and commit if there's a path to push back.

## Troubleshooting

### `mayapy -m pip install` fails with "Could not find a version that satisfies the requirement"

The wheel for the platform isn't in the bundle. Re-run Phase 1.1 with `--platform manylinux2014_x86_64` (Linux glibc 2.17+) and `--python-version 3.10` to match mayapy. If the studio runs an older glibc you may need `manylinux1_x86_64` or `manylinux2010_x86_64`; pip can take multiple `--platform` flags.

### Panel won't import — `ImportError: No module named 'PySide6'` (or 'PySide2')

`qtpy` couldn't find any Qt binding. Confirm it's installed: `mayapy -m pip show qtpy`. If it's there but still failing, check what binding mayapy actually has via `mayapy -c "import PySide2; print('ok')"` — if neither PySide2 nor PySide6 is importable, the Maya install is broken (not a maya-agent problem).

### Sidecar exits with `httpx.ConnectError`

Ollama server isn't running. Re-do step 2.5. Verify with `curl http://localhost:11434/api/tags`.

### Sidecar runs but the LLM returns garbage / non-JSON

`gemma4:31b` may not support Ollama's `format=json_schema` structured-output mode. Test with:

```bash
curl http://localhost:11434/api/chat -d '{
  "model": "gemma4:31b",
  "messages": [{"role":"user","content":"return JSON {\"ok\":true}"}],
  "format": "json",
  "stream": false
}'
```

If that works, escalate to schema-constrained: replace `"format": "json"` with `"format": {"type":"object","properties":{"ok":{"type":"boolean"}},"required":["ok"]}`. If structured-output fails, you'll need to either downgrade to a model that supports it or rework the prompt to use plain JSON mode + manual validation. Out of scope for v1.

### Auth handshake silently hangs

The session token file paths must match. The panel writes `~/.maya-agent/session-<MAYA_PID>.token`; the sidecar must read the same file via `--session-token-file`. PIDs differ between Maya invocations, so this token-file path will change every time Maya restarts. The panel's status row shows the current path — copy from there.

## Updating the studio

When `main` advances upstream and you want the changes at the studio:

1. On the connected machine: `git -C maya-agent pull` then `git -C maya-agent bundle create patch.bundle <last-deployed-ref>..HEAD`
2. Carry `patch.bundle` to the studio
3. At the studio: `git -C maya-agent bundle verify patch.bundle && git -C maya-agent pull patch.bundle main`

If a `pyproject.toml` change adds new runtime deps, repeat Phase 1.1/2.3 for the new wheels.
