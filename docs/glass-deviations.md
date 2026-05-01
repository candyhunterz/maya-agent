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
