"""playblast: render a viewport playblast to disk."""
from __future__ import annotations

from pydantic import Field
from tools_common import Tool, ToolArgs, ToolResult


class PlayblastArgs(ToolArgs):
    output_path: str = Field(..., description="Output file path (without extension).")
    start_frame: float | None = Field(None, description="First frame (defaults to current min).")
    end_frame: float | None = Field(None, description="Last frame (defaults to current max).")
    width: int = Field(1280, description="Image width.")
    height: int = Field(720, description="Image height.")


class Playblast(Tool):
    name = "playblast"
    description = (
        "Render a viewport playblast of the given frame range to the given output path. "
        "Read-only with respect to the scene (does not mutate animation data) but writes to disk."
    )
    args_model = PlayblastArgs
    mutating = False  # doesn't change scene state

    def execute(self, args, *, cancel_token=None):
        from maya import cmds
        try:
            start = args.start_frame
            end = args.end_frame
            if start is None:
                start = cmds.playbackOptions(query=True, minTime=True)
            if end is None:
                end = cmds.playbackOptions(query=True, maxTime=True)
            kwargs = {
                "filename": args.output_path,
                "startTime": start,
                "endTime": end,
                "width": args.width,
                "height": args.height,
                "format": "qt",
                "compression": "H.264",
                "viewer": False,
                "forceOverwrite": True,
            }
            result = cmds.playblast(**kwargs)
            return ToolResult(ok=True, value={"path": result, "frames": [start, end]})
        except Exception as e:
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")
