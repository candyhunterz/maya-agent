# Maya Agent v1 — Manual Smoke Test Instructions

This is the v1 success criterion that closes Task 14.2. A senior pipeline TD runs this once, end to end, on a machine with Maya 2024+ and Ollama installed, and records the result in `docs/smoke-test-<YYYY-MM-DD>.md`.

## Prerequisites

- **Maya 2024+** installed and licensed.
- **Ollama** installed, running, with the target model pulled:
  ```bash
  ollama pull gemma3:27b
  ollama serve
  ```
- **Python 3.10+** matching whatever Maya 2024 ships with for sidecar parity (or use the bundled `mayapy`/`python` from a venv).
- This repo cloned, `.venv` set up, `pip install -e ".[dev]"` done.

## Step 1 — Install the Maya module

```cmd
set MAYA_AGENT_MODEL=gemma3:27b
python scripts/install_into_maya.py --maya-version 2024
```

The script writes `<USER>\Documents\maya\2024\modules\maya-agent.mod` (Windows) or the platform equivalent. Restart Maya.

## Step 2 — Open the panel

In Maya's script editor (Python tab):

```python
import maya_agent.maya.maya_bootstrap as b
b.show_panel()
```

**Expected:** the *Maya Agent* dockable panel appears. Status row shows `● Disconnected — pipe at <path> | token-file: <path>`. The session token file should exist at `~/.maya-agent/session-<MAYA_PID>.token` with `0600` permissions on Linux/macOS.

## Step 3 — Open a scene with a known Euler discontinuity

Either a real test rig or a quickly-built one:

```python
from maya import cmds
cmds.file(new=True, force=True)
sphere = cmds.polySphere(name="test_sphere")[0]
cmds.setKeyframe(f"{sphere}.rotateY", time=1, value=10)
cmds.setKeyframe(f"{sphere}.rotateY", time=5, value=350)  # 340° jump
cmds.select(sphere)
```

## Step 4 — Start the sidecar

In a separate terminal (let `<PID>` be the PID of the Maya process; the panel's status row shows the full pipe path):

```bash
# Linux
python -m maya_agent.sidecar \
  --pipe /tmp/maya-agent-<PID>.sock \
  --session-token-file ~/.maya-agent/session-<PID>.token \
  --model gemma3:27b

# Windows (use the panel's Start agent button, or run the dev TCP-loopback fallback)
python -m maya_agent.sidecar ^
  --pipe 127.0.0.1:<PORT> ^
  --session-token-file %USERPROFILE%\.maya-agent\session-<PID>.token ^
  --model gemma3:27b
```

**Expected:** sidecar logs `Auth accepted; received inventory: 5 tools`. Panel status row turns green: `● Connected — sending inventory`. (On Windows, the `Start agent` button in the panel handles all of this for you.)

## Step 5 — Send a real intent

In the panel input field with the test sphere selected:

> find euler discontinuities on the selected control

Press *Send* (or `Ctrl+Enter`).

**Expected:**
- Tool entries appear inline in the chat:
  - `inspect_scene` ✓
  - `find_euler_discontinuities` ✓
- Final assistant message lists the discontinuity at frame 5 with a ~340° jump on `rotateY`.
- No errors in the panel or in the sidecar's stderr / `~/.maya-agent/logs/sidecar-<PID>.log`.

## Step 6 — Test mutating tools and undo

Send:

> fix it

**Expected:**
- `fix_euler_discontinuities` ✓ runs.
- After completion, click the panel's *Undo last* button (or press `Ctrl+Z` in Maya).
- The mutating tool's effect should reverse atomically — a single undo step should restore the pre-fix curve, AND walking back further should reverse the entire intent thanks to the outer per-intent chunk.

## Step 7 — Test disconnect/reconnect resilience

- Kill the sidecar process (`Ctrl+C` in its terminal).
- Panel status should turn back to `● Disconnected ...` within a second or two.
- Restart the sidecar with the same command.
- Panel status should turn green again. Send another intent — it should work.

## Step 8 — Test cancellation

- Send a long-ish intent (e.g., `inspect every node in deep mode and summarize`).
- While the agent is mid-loop, click the *■ Stop* button.
- The agent should stop on its next step boundary; panel should show a cancelled-style message; no further tool calls should fire.

## Step 9 — Document the result

Create `docs/smoke-test-<YYYY-MM-DD>.md`:

```markdown
# Maya Agent v1 — Smoke Test Result, <YYYY-MM-DD>

- **Maya version:** 2024.x
- **OS:** Linux (production target) / Windows 11 (dev)
- **Model:** gemma3:27b
- **Tester:** <name>

## Step results
- [✓] Panel appears, token file written
- [✓] Sidecar connects, inventory received
- [✓] inspect_scene + find_euler_discontinuities: discontinuity reported correctly
- [✓] fix_euler_discontinuities + Ctrl+Z: atomic undo works
- [✓] Disconnect/reconnect: status turns red, then green again
- [✓] Cancel mid-intent: agent stops cleanly

## Issues / observations
<freeform>

## Verdict
v1 PASS / FAIL.
```

Then commit:

```bash
git add docs/smoke-test-*.md
git commit -m "docs: v1 smoke-test passing record"
```

## Glass automation note

Glass (the AI implementer that produced this branch) cannot execute Steps 1–8 — they require running Maya, a live Ollama instance, and human judgment about the panel's visual feedback. Glass commits Task 14.1 (the docs and the *instructions* in this file) and stops there. The human runs the smoke test and writes the result file.
