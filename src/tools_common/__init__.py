"""Schemas and base classes shared between sidecar and Maya processes.

This package MUST NOT import maya.cmds. The eval harness loads tool classes
defined in this package (and in subclasses elsewhere) without a Maya install.
"""
from __future__ import annotations

from typing import ClassVar
from pydantic import BaseModel


class ToolArgs(BaseModel):
    """Base class for per-tool argument schemas. Subclass and add fields."""

    model_config = {"extra": "forbid"}


class ToolResult(BaseModel):
    """Result of a tool invocation. Either ok=True with value, or ok=False with error."""

    ok: bool
    value: object | None = None
    error: str | None = None


class Tool:
    """Base class for tools. Subclasses define class attributes and execute()."""

    name: ClassVar[str]
    description: ClassVar[str]
    args_model: ClassVar[type[ToolArgs]]
    mutating: ClassVar[bool] = False

    def execute(self, args, *, cancel_token=None) -> ToolResult:
        raise NotImplementedError

    @classmethod
    def to_inventory_entry(cls) -> dict:
        return {
            "name": cls.name,
            "description": cls.description,
            "json_schema": cls.args_model.model_json_schema(),
            "mutating": cls.mutating,
        }


__all__ = ["Tool", "ToolArgs", "ToolResult"]
