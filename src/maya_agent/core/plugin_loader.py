"""Plugin discovery and loading.

Walks paths from MAYA_AGENT_PLUGIN_PATHS (or an explicit list), validates each
.py module for a module-level maya import (forbidden), imports it, finds Tool
subclasses, and registers them. Fail-soft: errors on individual modules don't
abort the load.
"""
from __future__ import annotations

import ast
import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib  # 3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

from tools_common import Tool
from maya_agent.core.registry import ToolRegistry, RegistryError

_log = logging.getLogger(__name__)


@dataclass
class FailedModule:
    module_path: Path
    reason: str


@dataclass
class LoadSummary:
    loaded_count: int = 0
    shadowed_count: int = 0
    skipped_paths: list[Path] = field(default_factory=list)
    failed_modules: list[FailedModule] = field(default_factory=list)


def has_module_level_maya_import(source: str) -> bool:
    """True if the source has `import maya...` or `from maya...` at module scope."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in tree.body:  # only module-level
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "maya" or alias.name.startswith("maya."):
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "maya" or node.module.startswith("maya.")):
                return True
    return False


def _check_plugin_toml(path: Path, current_maya_version: str | None) -> bool:
    """Return True if the path should be loaded (or no plugin.toml). False if skipped."""
    toml_path = path / "plugin.toml"
    if not toml_path.exists():
        return True
    try:
        meta = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except Exception as e:
        _log.error("Failed to parse %s: %s", toml_path, e)
        return False
    min_v = meta.get("min_maya_version")
    if min_v and current_maya_version and current_maya_version < min_v:
        _log.warning(
            "Plugin %s requires Maya >= %s, current is %s — skipping",
            meta.get("name", path), min_v, current_maya_version,
        )
        return False
    max_v = meta.get("max_maya_version")
    if max_v and current_maya_version and current_maya_version > max_v:
        _log.warning(
            "Plugin %s requires Maya <= %s, current is %s — skipping",
            meta.get("name", path), max_v, current_maya_version,
        )
        return False
    return True


def _load_module(py_path: Path, summary: LoadSummary) -> object | None:
    source = py_path.read_text(encoding="utf-8")
    if has_module_level_maya_import(source):
        summary.failed_modules.append(FailedModule(py_path, "module-level maya import"))
        _log.error("Skipping %s: module-level maya import is disallowed", py_path)
        return None
    mod_name = f"_plugin_{py_path.stem}_{abs(hash(str(py_path)))}"
    spec = importlib.util.spec_from_file_location(mod_name, py_path)
    if spec is None or spec.loader is None:
        summary.failed_modules.append(FailedModule(py_path, "cannot create import spec"))
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        del sys.modules[mod_name]
        summary.failed_modules.append(FailedModule(py_path, f"{type(e).__name__}: {e}"))
        _log.exception("Failed to import %s", py_path)
        return None
    return mod


def _register_tools_from_module(mod: object, source_path: str,
                                registry: ToolRegistry, summary: LoadSummary) -> None:
    for attr_name in dir(mod):
        cls = getattr(mod, attr_name)
        if not isinstance(cls, type):
            continue
        if not issubclass(cls, Tool) or cls is Tool:
            continue
        if cls.__module__ != mod.__name__:
            continue  # imported from elsewhere; don't double-register
        try:
            if registry.register(cls, source_path):
                summary.loaded_count += 1
            else:
                summary.shadowed_count += 1
        except RegistryError as e:
            summary.failed_modules.append(FailedModule(Path(source_path), f"{cls.__name__}: {e}"))


def load_plugins_from_paths(
    paths: list[Path],
    registry: ToolRegistry,
    *,
    current_maya_version: str | None = None,
) -> LoadSummary:
    summary = LoadSummary()
    for path in paths:
        path = Path(path)
        if not path.exists():
            _log.warning("Plugin path does not exist: %s", path)
            continue
        if not _check_plugin_toml(path, current_maya_version):
            summary.skipped_paths.append(path)
            continue
        for py_path in sorted(path.rglob("*.py")):
            if py_path.name == "__init__.py":
                continue
            mod = _load_module(py_path, summary)
            if mod is not None:
                _register_tools_from_module(mod, str(path), registry, summary)
    _log.info(
        "Loaded %d tools from %d paths (%d shadowed, %d failed, %d paths skipped)",
        summary.loaded_count, len(paths), summary.shadowed_count,
        len(summary.failed_modules), len(summary.skipped_paths),
    )
    return summary
