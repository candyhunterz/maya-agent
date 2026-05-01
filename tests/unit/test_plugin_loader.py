from pathlib import Path
import textwrap
import pytest
from maya_agent.core.registry import ToolRegistry
from maya_agent.core.plugin_loader import (
    load_plugins_from_paths, has_module_level_maya_import,
)


def _write_tool(dir: Path, name: str, body: str) -> Path:
    f = dir / f"{name}.py"
    f.write_text(textwrap.dedent(body), encoding="utf-8")
    return f


GOOD_TOOL = """
    from pydantic import Field
    from tools_common import Tool, ToolArgs, ToolResult

    class _Args(ToolArgs):
        x: int = Field(..., description="X")

    class MyTool(Tool):
        name = "my_tool"
        description = "Does a thing."
        args_model = _Args
        def execute(self, args, *, cancel_token=None):
            from maya import cmds  # lazy
            return ToolResult(ok=True)
"""

BAD_TOOL_TOPLEVEL_IMPORT = """
    from maya import cmds  # MODULE LEVEL — disallowed
    from pydantic import Field
    from tools_common import Tool, ToolArgs, ToolResult

    class _Args(ToolArgs):
        x: int = Field(...)

    class MyTool(Tool):
        name = "my_tool"
        description = "..."
        args_model = _Args
        def execute(self, args, *, cancel_token=None):
            return ToolResult(ok=True)
"""

BROKEN_TOOL_IMPORT = """
    raise RuntimeError("boom at import time")
"""


def test_loader_loads_tool_from_directory(tmp_path):
    _write_tool(tmp_path, "my_tool", GOOD_TOOL)
    reg = ToolRegistry()
    summary = load_plugins_from_paths([tmp_path], reg)
    assert summary.loaded_count == 1
    assert summary.failed_modules == []
    assert reg.get("my_tool").name == "my_tool"


def test_loader_skips_modules_with_toplevel_maya_import(tmp_path):
    _write_tool(tmp_path, "bad_tool", BAD_TOOL_TOPLEVEL_IMPORT)
    reg = ToolRegistry()
    summary = load_plugins_from_paths([tmp_path], reg)
    assert summary.loaded_count == 0
    assert any("maya" in r.reason for r in summary.failed_modules)


def test_loader_continues_after_broken_module(tmp_path):
    _write_tool(tmp_path, "broken", BROKEN_TOOL_IMPORT)
    _write_tool(tmp_path, "good", GOOD_TOOL)
    reg = ToolRegistry()
    summary = load_plugins_from_paths([tmp_path], reg)
    assert summary.loaded_count == 1
    assert any(r.module_path.name == "broken.py" for r in summary.failed_modules)


def test_first_write_wins_across_paths(tmp_path):
    p1 = tmp_path / "p1"
    p2 = tmp_path / "p2"
    p1.mkdir(); p2.mkdir()
    _write_tool(p1, "my_tool", GOOD_TOOL)
    _write_tool(p2, "my_tool", GOOD_TOOL)  # same name in second path
    reg = ToolRegistry()
    summary = load_plugins_from_paths([p1, p2], reg)
    assert summary.loaded_count == 1
    assert summary.shadowed_count == 1


def test_plugin_toml_min_maya_version_skips(tmp_path):
    (tmp_path / "plugin.toml").write_text(textwrap.dedent("""
        name = "demo"
        version = "0.1.0"
        min_maya_version = "9999"
    """), encoding="utf-8")
    _write_tool(tmp_path, "my_tool", GOOD_TOOL)
    reg = ToolRegistry()
    summary = load_plugins_from_paths([tmp_path], reg, current_maya_version="2024")
    assert summary.loaded_count == 0
    assert summary.skipped_paths == [tmp_path]


def test_ast_lint_detects_various_import_forms():
    assert has_module_level_maya_import("from maya import cmds") is True
    assert has_module_level_maya_import("import maya.cmds") is True
    assert has_module_level_maya_import("import maya.cmds as cmds") is True
    assert has_module_level_maya_import("def f():\n    from maya import cmds") is False
    assert has_module_level_maya_import("import os") is False
