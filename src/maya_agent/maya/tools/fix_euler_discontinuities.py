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
