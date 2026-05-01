"""ToolDispatcher: validates args, wraps mutating tools in undo chunks, runs them.

Imports maya.cmds at module load. Outside Maya, this module won't import unless
a stub is patched in (the tests do exactly that).
"""
from __future__ import annotations

import inspect
import logging

try:
    from maya import cmds  # type: ignore
except ImportError:  # not in Maya — tests patch this module's `cmds` symbol
    cmds = None  # type: ignore

from pydantic import ValidationError

from tools_common import ToolResult
from maya_agent.core.registry import ToolRegistry, RegistryError

_log = logging.getLogger(__name__)


class ToolDispatcher:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def dispatch(self, tool_name: str, args: dict) -> ToolResult:
        try:
            tool_cls = self._registry.get(tool_name)
        except RegistryError as e:
            return ToolResult(ok=False, error=f"Unknown tool: {e}")

        try:
            parsed = tool_cls.args_model(**args)
        except ValidationError as e:
            return ToolResult(ok=False, error=f"Invalid arguments: {e}")

        tool = tool_cls()
        accepts_cancel = "cancel_token" in inspect.signature(tool.execute).parameters
        kwargs = {"cancel_token": None} if accepts_cancel else {}

        if tool_cls.mutating and cmds is not None:
            cmds.undoInfo(openChunk=True, chunkName=tool_name)
            try:
                return self._run(tool, parsed, kwargs)
            finally:
                cmds.undoInfo(closeChunk=True)
        else:
            return self._run(tool, parsed, kwargs)

    @staticmethod
    def _run(tool, parsed, kwargs) -> ToolResult:
        try:
            return tool.execute(parsed, **kwargs)
        except Exception as e:
            _log.exception("Tool raised")
            return ToolResult(ok=False, error=f"{type(e).__name__}: {e}")
