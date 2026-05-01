"""query_animation_curves: return key data for animation curves on given nodes."""
from __future__ import annotations

from pydantic import Field
from tools_common import Tool, ToolArgs, ToolResult


class QueryAnimationCurvesArgs(ToolArgs):
    objects: list[str] = Field(..., description="Node paths whose anim curves to inspect.")
    attributes: list[str] | None = Field(
        None, description="If given, only these attribute names (e.g., ['rotateX','rotateY']).")


class QueryAnimationCurves(Tool):
    name = "query_animation_curves"
    description = (
        "Return animation curve data for the given objects: keyframes (frame, value), "
        "tangent types, infinity types. Optionally filter to specific attributes. Read-only."
    )
    args_model = QueryAnimationCurvesArgs
    mutating = False

    def execute(self, args, *, cancel_token=None):
        from maya import cmds
        try:
            out: dict = {"curves": []}
            for obj in args.objects:
                if not cmds.objExists(obj):
                    continue
                attrs = args.attributes or cmds.listAttr(obj, keyable=True) or []
                for attr in attrs:
                    plug = f"{obj}.{attr}"
                    if not cmds.objExists(plug):
                        continue
                    curve_node = cmds.listConnections(plug, type="animCurve", source=True)
                    if not curve_node:
                        continue
                    cn = curve_node[0]
                    n = cmds.keyframe(cn, query=True, keyframeCount=True) or 0
                    if n == 0:
                        continue
                    times = cmds.keyframe(cn, query=True, timeChange=True) or []
                    values = cmds.keyframe(cn, query=True, valueChange=True) or []
                    out["curves"].append({
                        "object": obj, "attribute": attr, "curve": cn,
                        "keys": list(zip(times, values)),
                    })
            return ToolResult(ok=True, value=out)
        except Exception as e:
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")
