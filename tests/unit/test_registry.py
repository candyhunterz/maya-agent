import pytest
from pydantic import Field
from tools_common import Tool, ToolArgs
from maya_agent.core.registry import ToolRegistry, RegistryError


class _ArgsA(ToolArgs):
    x: int = Field(...)


class _ToolA(Tool):
    name = "tool_a"
    description = "First tool."
    args_model = _ArgsA
    def execute(self, args, *, cancel_token=None): ...


class _ArgsB(ToolArgs):
    y: str = Field(...)


class _ToolB(Tool):
    name = "tool_b"
    description = "Second tool."
    args_model = _ArgsB
    def execute(self, args, *, cancel_token=None): ...


class _ToolAClone(Tool):
    name = "tool_a"  # collides with _ToolA
    description = "Clone of A."
    args_model = _ArgsA
    def execute(self, args, *, cancel_token=None): ...


def test_register_tools_and_retrieve():
    r = ToolRegistry()
    assert r.register(_ToolA, "/path/a") is True
    assert r.register(_ToolB, "/path/a") is True
    assert r.get("tool_a") is _ToolA
    assert {t.name for t in r.all()} == {"tool_a", "tool_b"}


def test_first_write_wins_on_duplicate_name():
    r = ToolRegistry()
    assert r.register(_ToolA, "/path/early") is True
    assert r.register(_ToolAClone, "/path/late") is False
    # original wins
    assert r.get("tool_a") is _ToolA
    assert r.shadowed == [("tool_a", "/path/early", "/path/late")]


def test_inventory_returns_serializable_entries():
    r = ToolRegistry()
    r.register(_ToolA, "/x")
    inv = r.inventory()
    assert inv[0]["name"] == "tool_a"
    assert "json_schema" in inv[0]


def test_get_unknown_raises():
    r = ToolRegistry()
    with pytest.raises(RegistryError):
        r.get("missing")


def test_validate_tool_class_rejects_missing_name():
    class _Broken(Tool):
        description = "no name"
        args_model = _ArgsA
        def execute(self, args, *, cancel_token=None): ...
    r = ToolRegistry()
    with pytest.raises(RegistryError, match="name"):
        r.register(_Broken, "/x")


def test_validate_tool_class_rejects_non_snake_case():
    class _Args(ToolArgs):
        x: int = Field(...)
    class _Bad(Tool):
        name = "BadName"
        description = "ok"
        args_model = _Args
        def execute(self, args, *, cancel_token=None): ...
    r = ToolRegistry()
    with pytest.raises(RegistryError, match="snake_case"):
        r.register(_Bad, "/x")
