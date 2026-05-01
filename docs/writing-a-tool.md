# Writing a Tool

Tools are the unit of capability. Each tool is a `Tool` subclass with a name,
description, pydantic args model, and an `execute` method.

## Anatomy

```python
from pydantic import Field
from tools_common import Tool, ToolArgs, ToolResult


class MyToolArgs(ToolArgs):
    targets: list[str] = Field(..., description="Node paths to operate on.")
    mode: str = Field("default", description="One of 'default', 'aggressive'.")


class MyTool(Tool):
    name = "my_tool"
    description = "One-paragraph explanation aimed at the LLM. Be specific about effects and limits."
    args_model = MyToolArgs
    mutating = True   # set False for read-only tools

    def execute(self, args, *, cancel_token=None):
        from maya import cmds   # lazy: see lazy-import rule
        try:
            for target in args.targets:
                cmds.someOperation(target, mode=args.mode)
            return ToolResult(ok=True, value={"processed": args.targets})
        except Exception as e:
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")
```

## Batch by default — tools take lists, not singletons

**Tools should operate over lists of targets.** Prefer `targets: list[str]` over
`target: str`. The agent has a 20-step circuit breaker, and a workflow like
*"clean up the arms"* naturally hits 8+ FK controls × 2 arms × inspect+fix.
A singleton-per-call tool burns the budget on workflow shape rather than work.

Reasons:

1. **Step budget** — one batched call processes everything; doesn't pressure the
   agent's max-steps limit.
2. **Undo atomicity** — one tool call → one inner undo chunk wrapping the whole
   batch (plus the outer per-intent chunk). User undoes a whole batch with one
   keystroke.
3. **Round-trip cost** — one sidecar↔Maya frame, not N. Latency compounds.
4. **LLM reasoning** — the model's context shrinks: fewer turns to plan, fewer
   observations to track. Better outputs.

If a tool is genuinely scalar (e.g., `set_current_frame(frame: float)`), keep
it scalar. But anything that operates on nodes, attributes, or curves takes a
list. The five framework example tools all follow this — use them as
references.

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
