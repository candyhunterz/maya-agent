import pytest
from pydantic import Field
from tools_common import Tool, ToolArgs, ToolResult


class _MyArgs(ToolArgs):
    name: str = Field(..., description="A name")
    count: int = Field(1, description="How many")


class _MyTool(Tool):
    name = "my_tool"
    description = "Does a thing."
    args_model = _MyArgs
    mutating = True

    def execute(self, args, *, cancel_token=None):
        return ToolResult(ok=True, value={"got": args.name, "count": args.count})


def test_tool_inventory_entry_shape():
    entry = _MyTool.to_inventory_entry()
    assert entry["name"] == "my_tool"
    assert entry["description"] == "Does a thing."
    assert entry["mutating"] is True
    assert entry["json_schema"]["type"] == "object"
    assert "name" in entry["json_schema"]["properties"]
    assert "count" in entry["json_schema"]["properties"]


def test_tool_executes_with_parsed_args():
    tool = _MyTool()
    result = tool.execute(_MyArgs(name="foo", count=3))
    assert result.ok is True
    assert result.value == {"got": "foo", "count": 3}


def test_tool_result_failure_shape():
    r = ToolResult(ok=False, error="bad input")
    assert r.ok is False
    assert r.error == "bad input"
    assert r.value is None


def test_tool_args_validation_rejects_wrong_types():
    with pytest.raises(Exception):
        _MyArgs(name=123, count="not_an_int")
