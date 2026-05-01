"""find_euler_discontinuities: locate frames where rotation channels jump."""
from __future__ import annotations

from pydantic import Field
from tools_common import Tool, ToolArgs, ToolResult


class FindEulerDiscontinuitiesArgs(ToolArgs):
    objects: list[str] = Field(..., description="Node paths to inspect.")
    threshold_degrees: float = Field(
        180.0, description="Frame-to-frame jump magnitude that counts as a discontinuity.")


class FindEulerDiscontinuities(Tool):
    name = "find_euler_discontinuities"
    description = (
        "Locate frames on the given objects where rotation channels (rotateX/Y/Z) jump "
        "by more than threshold_degrees between consecutive keys, indicating Euler "
        "discontinuities. Read-only. Returns list of (object, attribute, frame, jump_degrees)."
    )
    args_model = FindEulerDiscontinuitiesArgs
    mutating = False

    def execute(self, args, *, cancel_token=None):
        from maya import cmds
        try:
            results = []
            for obj in args.objects:
                for attr in ("rotateX", "rotateY", "rotateZ"):
                    plug = f"{obj}.{attr}"
                    if not cmds.objExists(plug):
                        continue
                    curve_node = cmds.listConnections(plug, type="animCurve", source=True)
                    if not curve_node:
                        continue
                    cn = curve_node[0]
                    times = cmds.keyframe(cn, query=True, timeChange=True) or []
                    values = cmds.keyframe(cn, query=True, valueChange=True) or []
                    for i in range(1, len(values)):
                        jump = abs(values[i] - values[i - 1])
                        if jump > args.threshold_degrees:
                            results.append({
                                "object": obj, "attribute": attr,
                                "frame": times[i], "jump_degrees": jump,
                            })
            return ToolResult(ok=True, value={"discontinuities": results})
        except Exception as e:
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")
