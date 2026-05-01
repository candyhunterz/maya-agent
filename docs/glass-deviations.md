# Glass Deviations Log — Maya Agent v1

Append-only log of every place where Glass adapted away from the plan's literal code.

## Task 1.1 — `.gitignore` augmented with local environment artifacts
**Plan said:** `.gitignore` contains exactly 15 entries (the standard Python/IDE/log set).
**Actually used:** Plan's 15 entries plus a trailing block adding `.glass/` and `.mcp.json`.
**Why:** The working tree already contained a `.glass/` directory (Glass orchestrator's iteration data) and a `.mcp.json` file (local MCP server config) before scaffolding. Both are local-machine artifacts unrelated to the project source. The plan's Step 6 uses `git add .`, which would otherwise stage them on the first commit. Adding two ignore lines is the minimum-impact way to honor the plan's `git add .` while keeping the commit free of personal-environment files.

## Task 3.2 — `_write_tool` test helper specifies `encoding="utf-8"`
**Plan said:** `f.write_text(textwrap.dedent(body))` and `(tmp_path / "plugin.toml").write_text(...)` with no `encoding` argument.
**Actually used:** Both calls take `encoding="utf-8"`.
**Why:** The plan's `BAD_TOOL_TOPLEVEL_IMPORT` fixture contains an em-dash (`—`). On Windows, `Path.write_text` defaults to the OEM/locale codepage (cp1252), which encodes that character as byte 0x97. The plugin loader (per the plan) reads files with `read_text(encoding="utf-8")`, which then raises `UnicodeDecodeError`. Forcing UTF-8 on the writes makes the test deterministic across OSes without changing the loader's contract (UTF-8 source files are the right assumption for Python plugins).

## Task 12.1 — `_consume_one` MatchError message includes the word "extra"
**Plan said:** When in `allow_extra=False` mode the matcher raises `MatchError(f"expected {tool} at position {start}, got {name} (args={args})")`.
**Actually used:** Same message but with "got extra unexpected call" in place of "got" so the test's `pytest.raises(MatchError, match="extra")` regex matches.
**Why:** The plan's `test_allow_extra_false_rejects_extras` expects the error to match the regex `"extra"`, but the plan's literal implementation never emits that word in the strict-mode rejection path. Adjusting the message text (one phrase) is the smallest change that reconciles the plan's own test with the implementation. Semantics are unchanged.

## Task 13.1 — `test_eval_case` skips when recording is absent
**Plan said:** Each parameterized case calls `build_llm_client(...)` directly. In auto/replay mode, if no recording exists, the runner falls back to a live `OllamaClient` which dies on first request when Ollama isn't running.
**Actually used:** Added a guard in `test_eval_cases.py::test_eval_case` that calls `pytest.skip(...)` when `mode in ("auto", "replay")` and the recording file is absent.
**Why:** PRD Definition-of-done #3 requires `pytest tests/eval -q` to "skip cleanly with a message indicating recordings are needed" when recordings are unavailable. With Ollama down on this dev machine and no recordings yet (Task 13.2 is deferred per PRD), the unmodified runner failed six cases instead of skipping. The skip aligns the plan output with the PRD's ship gate.
