"""inspect_scene: return current selection, namespaces, scene path, framerate."""
from __future__ import annotations

from pydantic import Field
from tools_common import Tool, ToolArgs, ToolResult


class InspectSceneArgs(ToolArgs):
    deep: bool = Field(False, description="Include all nodes (slow on big scenes); else summary only.")


class InspectScene(Tool):
    name = "inspect_scene"
    description = (
        "Return a summary of the current Maya scene: selection, namespaces, scene path, "
        "framerate, time range. Set deep=true to include a full node list (slow). Read-only."
    )
    args_model = InspectSceneArgs
    mutating = False

    def execute(self, args, *, cancel_token=None):
        from maya import cmds
        try:
            selection = cmds.ls(selection=True, long=True) or []
            namespaces = [n for n in (cmds.namespaceInfo(listOnlyNamespaces=True, recurse=True) or [])
                          if n not in ("UI", "shared")]
            scene_path = cmds.file(query=True, sceneName=True) or ""
            framerate = cmds.currentUnit(query=True, time=True)
            min_t = cmds.playbackOptions(query=True, minTime=True)
            max_t = cmds.playbackOptions(query=True, maxTime=True)
            value = {
                "selection": selection,
                "namespaces": namespaces,
                "scene_path": scene_path,
                "framerate": framerate,
                "frame_range": [min_t, max_t],
            }
            if args.deep:
                value["all_nodes"] = cmds.ls(long=True) or []
            return ToolResult(ok=True, value=value)
        except Exception as e:
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")
