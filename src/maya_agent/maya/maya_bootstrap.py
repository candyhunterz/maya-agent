"""Maya bootstrap: registers the panel as a workspaceControl, loads plugins.

Called from userSetup.py (or a shelf button) inside Maya. Not importable
outside Maya (uses maya.cmds and PySide6 widget integration).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from maya import cmds
from PySide6 import QtWidgets

from maya_agent.core.plugin_loader import load_plugins_from_paths
from maya_agent.core.registry import ToolRegistry

_log = logging.getLogger(__name__)
_PANEL_OBJECT_NAME = "MayaAgentPanel"


def _build_registry() -> tuple[ToolRegistry, list[str]]:
    reg = ToolRegistry()
    paths: list[Path] = []
    env_paths = os.environ.get("MAYA_AGENT_PLUGIN_PATHS", "")
    for p in env_paths.split(os.pathsep):
        p = p.strip()
        if p:
            paths.append(Path(p))
    # Append framework example tools
    examples = Path(__file__).parent / "tools"
    if examples.exists():
        paths.append(examples)
    summary = load_plugins_from_paths(paths, reg, current_maya_version=cmds.about(version=True))
    warnings = [f"{f.module_path.name}: {f.reason}" for f in summary.failed_modules]
    return reg, warnings


def show_panel() -> None:
    """Create or focus the Maya Agent dockable panel."""
    from maya_agent.maya.panel import MayaAgentPanel  # late import (PySide6 needs Maya UI)

    if cmds.workspaceControl(_PANEL_OBJECT_NAME, exists=True):
        cmds.workspaceControl(_PANEL_OBJECT_NAME, edit=True, restore=True)
        return

    cmds.workspaceControl(
        _PANEL_OBJECT_NAME, label="Maya Agent",
        retain=False, floating=True,
    )

    registry, warnings = _build_registry()
    panel = MayaAgentPanel(registry)
    panel.show_plugin_warnings(warnings)

    # Parent the panel widget to the workspaceControl
    ctrl_widget = _qt_widget_for_workspace_control(_PANEL_OBJECT_NAME)
    layout = QtWidgets.QVBoxLayout(ctrl_widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(panel)


def _qt_widget_for_workspace_control(name: str) -> QtWidgets.QWidget:
    """Find the QWidget for a workspaceControl by name."""
    from shiboken6 import wrapInstance
    from maya.OpenMayaUI import MQtUtil
    ptr = MQtUtil.findControl(name)
    if ptr is None:
        raise RuntimeError(f"Could not find workspaceControl: {name}")
    return wrapInstance(int(ptr), QtWidgets.QWidget)
