# Maya Agent v1 — PRD for Glass

> **Audience:** Glass orchestrator (the user's Rust terminal+AI orchestrator).
> **Purpose:** Direct an autonomous AI implementer to ship Maya Agent v1 against the committed spec and plan.

## Goal

Implement Maya Agent v1 — a sidecar Python process that talks to Ollama and a Qt-paneled command server inside Maya, executing curated tools per natural-language intent. End state: all 14 phases of the plan complete, unit tests pass, eval harness runs cleanly in replay mode (or skips with documented reason if recordings unavailable), manual smoke-test instructions ready for the human to execute.

## Authoritative artifacts

These three documents are the source of truth, in this order of precedence:

1. **Spec:** `docs/superpowers/specs/2026-05-01-maya-agent-v1-design.md`
   - Design rationale, architectural decisions, contracts, non-goals, risks
   - Used to interpret "why" and to resolve ambiguity in the plan
2. **Plan:** `docs/superpowers/plans/2026-05-01-maya-agent-v1-implementation.md`
   - 14 phases, ~30 tasks, each with explicit Files / TDD Steps / Commit message
   - The work order — execute it task-by-task in order
3. **This PRD:** `PRD.md`
   - Execution policy, constraints, status reporting, escalation rules

When the plan and spec disagree, the spec wins. Flag the disagreement in `docs/glass-deviations.md` before deviating.

## Runtime context

- **OS:**
  - Development environment (this machine): Windows 11
  - **Studio production target: Linux** (this is where the framework will actually be used)
  - Code must work on both. The transport layer hides the OS distinction. The Linux path uses `asyncio.open_unix_connection` against a unix domain socket and is the clean, well-supported path. The Windows dev path uses TCP loopback as a workaround — see Known plan gaps below.
- **Python:** 3.10+
- **Maya:** 2024+ (only relevant for the manual smoke test in Phase 14)
- **Ollama:** required only for Phase 13 recording and Task 4.3's optional manual smoke; CI replay mode does not require Ollama
- **Working directory:** the repo root (`C:\Users\nkngu\apps\maya-agent`)

## Branch policy

- Create and work on branch `feature/v1-implementation` off `main`. Do not commit to `main` directly.
- Do not push to remote (no `git push`) unless explicitly told.
- One commit per task, using the exact commit message specified in the plan's Commit step. Do not squash, amend, or rebase.
- Never use `--no-verify` or `--no-gpg-sign`.

## Per-task workflow

The plan is structured as Phases (1–14), each containing numbered Tasks (e.g., `Task 6.2`). Each task block contains:

- A **Files** section listing exact paths to create/modify
- Numbered **Steps** (typically TDD: failing test → run-fail → implement → run-pass → commit)
- An explicit **Commit** step with the exact commit message

For each task, in order:

1. Read the entire task block before starting.
2. Execute every Step in order. Do not skip the "run test to verify it fails" step — TDD discipline is part of the contract.
3. When the Step says "Run: `<command>`", run that command and verify it produces the Expected output before moving on.
4. Use the exact commit message specified. Do not add or remove a `Co-Authored-By` line that's already part of the message.
5. After the commit, run `pytest tests/unit -q` and verify the full suite still passes (regressions in earlier tasks block the next task).
6. Append a one-line entry to `docs/glass-progress.md`:
   ```
   2026-05-01 14:32 — Task 6.2 complete (AgentLoop happy-path; 24 unit tests passing)
   ```

## Phase boundaries

After the last task of a phase commits cleanly, append a phase-summary line:

```
2026-05-01 15:10 — Phase 6 complete (5 tasks, 24/24 unit tests passing)
```

Run `pytest tests/unit -q` and `pytest tests/eval -q` (the latter may skip if no recordings); capture pass/fail counts in the entry.

## Tasks requiring external resources

These tasks reference resources that may not be available; honor the skip rules:

- **Task 4.3 Step 2 (smoke-test against local Ollama):** If `OLLAMA_BASE_URL` (default `http://localhost:11434`) does not respond, skip the manual smoke step. The OllamaClient code itself has no Ollama dependency at install/test time — only the smoke step does. Note the skip in `docs/glass-progress.md`.

- **Task 13.2 (record initial LLM responses):** Requires Ollama running with `gemma3:27b` pulled. If unavailable:
  - Do NOT fabricate recordings.
  - Do NOT mark Phase 13 complete.
  - Do commit Task 13.1 (the case JSON files) — those are independent of Ollama.
  - Add to `docs/glass-summary.md` at the end that Phase 13.2 is deferred pending an Ollama-equipped environment.

- **Task 14.2 (manual smoke test in Maya):** This is the human's responsibility, not Glass's. After Task 14.1 commits, write `docs/smoke-test-instructions.md` summarizing the steps the human will follow. Do NOT attempt to launch Maya, run the panel, or claim success on this task.

## Mandatory in v1 (do not skip these — they are not optional)

After external review, two additions became v1-mandatory:

- **Auth handshake.** Both transports require a session-token handshake. Maya panel generates the token at startup, writes to `~/.maya-agent/session-<pid>.token` (0600), and only sends `tool_inventory` after the sidecar's first message is a valid `AuthMessage`. The sidecar reads the token from `--session-token-file` (CLI) or `MAYA_AGENT_SESSION_TOKEN` (env) and sends `AuthMessage` as its first frame. Mismatched tokens cause silent connection drop. Implementation is fully specified across Task 2.2 (protocol), Task 7.1 (sidecar), Task 8.1 (server), Task 9.1 (panel) — Glass must wire all four.

- **Outer per-intent undo chunk.** The panel opens `cmds.undoInfo(openChunk=True, chunkName=f"agent: {short_intent_text}")` when sending a `user_intent`, closes on `intent_finished` or `intent_failed`. Nests with per-tool inner chunks. Implementation in Task 9.1.

## Known plan gaps — do not fix unilaterally

The following are deliberate v1 limitations the plan acknowledges. Glass should NOT try to "fix" them by writing extra code:

- **Windows named-pipe transport is a dev-only workaround** (Task 5.1, Task 7.1): asyncio doesn't natively support Windows named pipes for client connect. The plan falls back to TCP loopback for the sidecar's connect side on Windows (sidecar accepts `host:port` via `--pipe`). **This limitation is Windows-dev-only — it does NOT apply to the Linux studio production target.** On Linux, `asyncio.open_unix_connection` connects to the unix domain socket created by Maya's `QLocalServer` natively, no workaround needed. Glass must not "fix" the Windows path by writing a custom Windows named-pipe implementation; the production target doesn't need it, and the Windows TCP loopback is sufficient for the personal-machine smoke test. The Maya-side `QLocalServer` correctly uses named pipes on Windows and unix domain sockets on Linux — Qt handles that transparently. **Note:** the auth handshake closes the security gap that the TCP loopback would otherwise create.

- **Eval inventory hardcoded in `tests/eval/test_eval_cases.py`** (Task 12.2): `EVAL_INVENTORY` is a literal in the test file rather than dynamically built from real tool classes. This is intentional — it lets eval run without importing any tool implementation modules. Do not refactor to import tool classes.

- **Pydantic v2 discriminator API** (Task 2.2): The plan uses `TypeAdapter(Message, config={"discriminator": "type"})`. If the installed pydantic version's API differs (e.g., requires `Field(discriminator="type")` or a `RootModel` wrapper), use whichever pattern actually works in the installed version and document the deviation in `docs/glass-deviations.md`.

- **Python 3.10 `tomllib` import** (Task 3.2): `tomllib` is stdlib in 3.11+. The plan notes a fallback (`try: import tomllib; except ImportError: import tomli as tomllib`). If 3.10, add `tomli` to `pyproject.toml` dev deps and use the fallback.

## Constraints

### Do
- Use the exact file paths specified in each task
- Use the exact commit message specified in each task's Commit step
- Run the test commands the plan specifies and verify expected output
- If a test fails after implementing per the plan and the implementation is correct, debug — the plan is fallible
- If a deviation is genuinely required (library API changed, etc.), make the deviation, document it in `docs/glass-deviations.md` with a paragraph explaining why
- Halt and write to `docs/glass-questions.md` if blocked for more than ~3 retry attempts on the same issue

### Do not
- Push to a remote
- Edit `docs/superpowers/specs/` or `docs/superpowers/plans/` (those are sealed for this run)
- Skip TDD steps — write the failing test first, every time, even if it feels redundant
- Use `git commit --amend`, `git commit --no-verify`, or `git rebase`
- Modify `pyproject.toml` after Phase 1 except to add a missing dependency that a later task explicitly requires (e.g., `tomli` for 3.10)
- Install pip packages outside what's declared in `pyproject.toml`
- Delete or rewrite history
- Implement anything in the spec's "Non-Goals" section, even if it seems convenient (see Out of Scope below)
- Add files not specified in the plan unless required to make a specified test pass

### Out of scope (explicit non-goals from the spec)

Do not implement these even if convenient:

- Scene-state checkpoints
- Confirmation gating for "dangerous" tools (per-tool flag — superseded by the v1.5 `scope_estimator` design)
- `scope_estimator` hook on tools — **v1.5 design captured in spec; not v1.** Do not add a `scope_estimator` method to the `Tool` ABC, do not wire any `scope_warning` message into the protocol, do not add threshold config.
- Scene-state digest for divergence detection — **v1.5 design captured in spec; not v1.** Do not add `_scene_digest()` to the dispatcher, do not capture state per intent, do not return `scene_diverged` errors. Spec tags this as the gating issue for studio rollout, not v1.
- Hot reload of plugins
- Streaming token-level responses
- Parallel tool calls
- Multi-agent / planner-executor split
- RAG / vector knowledge base
- Disk persistence of chat history or cross-intent memory
- Stale-replacement of older observations (deferred per spec)
- Prompt caching (deferred until Gemma 4 at the studio)
- Live integration eval execution against `mayapy` (stub file only)
- Telemetry beyond stdlib `logging`

## Status tracking

Glass writes to these files at repo root, creating them if missing. They are deliberately outside `docs/superpowers/` so they don't pollute the spec/plan archive:

- **`docs/glass-progress.md`** — append-only log. One line per task completion, one line per phase summary. Format:
  ```
  YYYY-MM-DD HH:MM — Task N.M complete (<short description>; <test count> unit tests passing)
  YYYY-MM-DD HH:MM — Phase N complete (<task count> tasks, <unit pass>/<unit total> unit, <eval pass>/<eval total> eval)
  ```

- **`docs/glass-deviations.md`** — append-only. Every time the plan's literal code doesn't work and Glass adapts, log it:
  ```
  ## Task N.M — <short title>
  **Plan said:** <what the plan specified>
  **Actually used:** <what was implemented>
  **Why:** <one-paragraph explanation>
  ```

- **`docs/glass-questions.md`** — append-only. Blockers needing human attention. Glass halts execution after writing here:
  ```
  ## Task N.M — <blocker title>
  <description of what's blocking, what was tried, what's needed from the human>
  ```

- **`docs/glass-summary.md`** — overwritten at end with the final state (see "Definition of done" below).

These files are committed alongside the work — each progress entry can go into the same commit as the task it documents, or into a separate commit at phase boundaries. Glass's choice; just be consistent.

## Escalation

Halt execution and write to `docs/glass-questions.md` if any of these occur:

- A test fails repeatedly (>3 attempts) after implementing per the plan and a reasonable debug attempt
- A library API has changed in a way that breaks more than one task's code blocks
- A task references something that doesn't exist (a function, a path, a tool import that won't resolve)
- A commit attempt produces unexpected git state (uncommitted files Glass didn't author, branch in detached HEAD, mid-rebase, etc.)
- The plan's instructions are genuinely ambiguous and the spec doesn't disambiguate
- More than 5 tasks have required deviations — likely a systemic issue worth pausing for

Do NOT silently work around these. The human needs to see them.

## Definition of done

The v1 ship gate is met when ALL of these hold:

1. All 14 phases marked complete in `docs/glass-progress.md` (Phase 13.2 may be marked "deferred — Ollama unavailable" with explanation; that is acceptable for the v1 ship gate)
2. `pytest tests/unit -q` exits 0 with all unit tests passing
3. `pytest tests/eval -q` either:
   - Passes (if recordings present), OR
   - Skips cleanly with a message indicating recordings are needed
4. `git log --oneline feature/v1-implementation` shows the expected sequence of one commit per task
5. `docs/glass-summary.md` exists and contains the final state per the schema below

## Final summary schema

When the definition of done is met, write `docs/glass-summary.md` with this structure:

```markdown
# Maya Agent v1 — Glass Implementation Summary

**Branch:** feature/v1-implementation
**Started:** YYYY-MM-DD HH:MM
**Completed:** YYYY-MM-DD HH:MM
**Total commits:** N

## Phase status
- Phase 1: ✅ complete
- Phase 2: ✅ complete
- ...
- Phase 13: ⚠ deferred — Ollama unavailable; case JSONs committed, recordings pending
- Phase 14: ✅ docs complete; manual smoke test pending human action

## Test status
- Unit: <pass>/<total>
- Eval: <pass>/<total> or "skipped — no recordings"

## Deviations from plan
- See `docs/glass-deviations.md` (or "none" if file empty)

## Open questions
- See `docs/glass-questions.md` (or "none" if file empty)

## Suggested next human action
1. Run the manual smoke test per `docs/smoke-test-instructions.md`
2. (If Phase 13 deferred) Spin up Ollama with gemma3:27b and run `MAYA_AGENT_EVAL_MODE=record pytest tests/eval/`
3. Review the implementation: `git log --oneline feature/v1-implementation`
```

---

**Acknowledgment:** Glass should treat this PRD as immutable for the duration of the run. If the PRD itself appears wrong, halt and write to `docs/glass-questions.md`.
