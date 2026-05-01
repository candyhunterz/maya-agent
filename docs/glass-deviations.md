# Glass Deviations Log — Maya Agent v1

Append-only log of every place where Glass adapted away from the plan's literal code.

## Task 1.1 — `.gitignore` augmented with local environment artifacts
**Plan said:** `.gitignore` contains exactly 15 entries (the standard Python/IDE/log set).
**Actually used:** Plan's 15 entries plus a trailing block adding `.glass/` and `.mcp.json`.
**Why:** The working tree already contained a `.glass/` directory (Glass orchestrator's iteration data) and a `.mcp.json` file (local MCP server config) before scaffolding. Both are local-machine artifacts unrelated to the project source. The plan's Step 6 uses `git add .`, which would otherwise stage them on the first commit. Adding two ignore lines is the minimum-impact way to honor the plan's `git add .` while keeping the commit free of personal-environment files.
