"""ToolRegistry: holds the loaded tools, validates them, handles override semantics."""
from __future__ import annotations

import logging
import re
from tools_common import Tool, ToolArgs

_log = logging.getLogger(__name__)
_SNAKE_CASE = re.compile(r"^[a-z][a-z0-9_]*$")


class RegistryError(Exception):
    """Raised on invalid tool registration or unknown tool lookup."""


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, type[Tool]] = {}
        self._sources: dict[str, str] = {}
        self.shadowed: list[tuple[str, str, str]] = []

    def register(self, tool_cls: type[Tool], source_path: str) -> bool:
        """Validate and register a tool class. Returns True if registered, False if shadowed."""
        self._validate(tool_cls)
        name = tool_cls.name
        if name in self._tools:
            winner = self._sources[name]
            self.shadowed.append((name, winner, source_path))
            _log.warning(
                "Tool '%s' from %s shadowed by earlier registration from %s",
                name, source_path, winner,
            )
            return False
        self._tools[name] = tool_cls
        self._sources[name] = source_path
        return True

    def get(self, name: str) -> type[Tool]:
        if name not in self._tools:
            raise RegistryError(f"Unknown tool: {name!r}")
        return self._tools[name]

    def all(self) -> list[type[Tool]]:
        return list(self._tools.values())

    def inventory(self) -> list[dict]:
        return [t.to_inventory_entry() for t in self._tools.values()]

    @staticmethod
    def _validate(cls: type[Tool]) -> None:
        if not getattr(cls, "name", None):
            raise RegistryError(f"{cls.__name__}.name not set or empty")
        if not _SNAKE_CASE.match(cls.name):
            raise RegistryError(f"{cls.__name__}.name {cls.name!r} is not snake_case")
        if not getattr(cls, "description", None):
            raise RegistryError(f"{cls.__name__}.description not set or empty")
        am = getattr(cls, "args_model", None)
        if am is None or not (isinstance(am, type) and issubclass(am, ToolArgs)):
            raise RegistryError(f"{cls.__name__}.args_model must be a ToolArgs subclass")
        try:
            am.model_json_schema()
        except Exception as e:
            raise RegistryError(f"{cls.__name__}.args_model schema invalid: {e}") from e
        if cls.execute is Tool.execute:
            raise RegistryError(f"{cls.__name__} must override execute()")
