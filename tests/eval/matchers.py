"""Sequence matchers for eval expected_calls.

Three matcher types:
  - bare string: exact tool name in this position
  - {tool, args_contain}: positional + partial arg match
  - {any_order: [...]}: all listed tools must appear, order within block flexible
"""
from __future__ import annotations

from typing import Any


class MatchError(AssertionError):
    pass


def _arg_matches(actual: dict, required: dict) -> bool:
    return all(actual.get(k) == v for k, v in required.items())


def assert_calls_match(
    actual: list[tuple[str, dict]],
    expected: list[Any],
    *,
    allow_extra: bool,
) -> None:
    """actual: list of (tool_name, args) recorded during the eval run.
    expected: list of matcher elements (str | {tool, args_contain} | {any_order: [...]}).
    """
    i = 0  # actual index
    for matcher in expected:
        if isinstance(matcher, str):
            i = _consume_one(actual, i, matcher, None, allow_extra)
        elif isinstance(matcher, dict) and "any_order" in matcher:
            i = _consume_any_order(actual, i, matcher["any_order"], allow_extra)
        elif isinstance(matcher, dict) and "tool" in matcher:
            i = _consume_one(actual, i, matcher["tool"], matcher.get("args_contain"), allow_extra)
        else:
            raise ValueError(f"Unknown matcher: {matcher!r}")
    if not allow_extra and i != len(actual):
        raise MatchError(f"extra unexpected calls after position {i}: {actual[i:]}")


def _consume_one(actual, start, tool, args_required, allow_extra):
    j = start
    while j < len(actual):
        name, args = actual[j]
        if name == tool and (args_required is None or _arg_matches(args, args_required)):
            return j + 1
        if not allow_extra:
            raise MatchError(
                f"expected {tool} at position {start}, got extra unexpected call "
                f"{name} (args={args})"
            )
        j += 1
    raise MatchError(f"expected {tool} not found starting at position {start}; "
                     f"args needed: {args_required}; remaining: {actual[start:]}")


def _consume_any_order(actual, start, names, allow_extra):
    needed = list(names)
    j = start
    while needed and j < len(actual):
        name, _ = actual[j]
        if name in needed:
            needed.remove(name)
            j += 1
        elif allow_extra:
            j += 1
        else:
            raise MatchError(
                f"any_order block needs {needed} but got {name} at position {j}"
            )
    if needed:
        raise MatchError(f"any_order block missing: {needed}")
    return j
