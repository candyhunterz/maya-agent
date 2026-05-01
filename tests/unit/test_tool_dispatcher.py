from unittest.mock import MagicMock, patch
from pydantic import Field
from tools_common import Tool, ToolArgs, ToolResult
from maya_agent.core.registry import ToolRegistry
from maya_agent.maya.tool_dispatcher import ToolDispatcher


class _Args(ToolArgs):
    x: int = Field(...)


class _MutTool(Tool):
    name = "mut"
    description = "Mutates."
    args_model = _Args
    mutating = True
    def execute(self, args, *, cancel_token=None):
        return ToolResult(ok=True, value={"got": args.x})


class _ReadTool(Tool):
    name = "read"
    description = "Reads."
    args_model = _Args
    mutating = False
    def execute(self, args, *, cancel_token=None):
        return ToolResult(ok=True, value={"got": args.x})


def _make_dispatcher():
    reg = ToolRegistry()
    reg.register(_MutTool, "/")
    reg.register(_ReadTool, "/")
    return ToolDispatcher(reg)


def test_dispatcher_validates_args_and_returns_result():
    d = _make_dispatcher()
    with patch("maya_agent.maya.tool_dispatcher.cmds") as cmds:
        result = d.dispatch("read", {"x": 5})
        assert result.ok is True
        assert result.value == {"got": 5}
        # read tool should not open undo chunk
        cmds.undoInfo.assert_not_called()


def test_dispatcher_wraps_mutating_tool_in_undo_chunk():
    d = _make_dispatcher()
    with patch("maya_agent.maya.tool_dispatcher.cmds") as cmds:
        result = d.dispatch("mut", {"x": 7})
        assert result.ok is True
        # openChunk + closeChunk
        calls = [c for c in cmds.undoInfo.call_args_list]
        assert any(call.kwargs.get("openChunk") for call in calls)
        assert any(call.kwargs.get("closeChunk") for call in calls)


def test_dispatcher_returns_error_on_validation_failure():
    d = _make_dispatcher()
    result = d.dispatch("mut", {})  # missing x
    assert result.ok is False
    assert "x" in (result.error or "")


def test_dispatcher_returns_error_on_unknown_tool():
    d = _make_dispatcher()
    result = d.dispatch("nope", {"x": 1})
    assert result.ok is False
    assert "unknown" in (result.error or "").lower()


def test_dispatcher_catches_tool_exceptions_and_closes_chunk():
    class _BoomArgs(ToolArgs):
        x: int = Field(...)
    class _Boom(Tool):
        name = "boom"; description = "Boom."; args_model = _BoomArgs; mutating = True
        def execute(self, args, *, cancel_token=None):
            raise ValueError("crash")
    reg = ToolRegistry()
    reg.register(_Boom, "/")
    d = ToolDispatcher(reg)
    with patch("maya_agent.maya.tool_dispatcher.cmds") as cmds:
        result = d.dispatch("boom", {"x": 1})
        assert result.ok is False
        assert "ValueError" in (result.error or "") and "crash" in (result.error or "")
        # closeChunk must still be called
        assert any(call.kwargs.get("closeChunk") for call in cmds.undoInfo.call_args_list)
