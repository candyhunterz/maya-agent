"""Regression guard: Maya code must import Qt through qtpy, not PySide2/PySide6
directly. The studio target is Maya 2024 (PySide2); dev target is often Maya
2025+ (PySide6). Direct binding imports break one or the other.
"""
from __future__ import annotations

import re
from pathlib import Path

MAYA_DIR = Path(__file__).resolve().parent.parent.parent / "src" / "maya_agent" / "maya"
FORBIDDEN = re.compile(r"^\s*(from|import)\s+PySide[26]\b", re.MULTILINE)


def test_no_direct_pyside_imports_in_maya_package() -> None:
    offenders: list[str] = []
    for py in MAYA_DIR.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if FORBIDDEN.search(text):
            offenders.append(str(py.relative_to(MAYA_DIR.parent.parent.parent)))
    assert not offenders, (
        "Maya package must import Qt via qtpy, not PySide2/PySide6 directly. "
        f"Offending files: {offenders}"
    )
