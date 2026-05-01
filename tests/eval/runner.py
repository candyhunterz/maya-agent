"""Eval runner: loads case JSON, builds a fake MayaClient, runs AgentLoop."""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maya_agent.sidecar.agent_loop import AgentLoop, IntentRequest
from maya_agent.sidecar.llm_client import LLMClient
from maya_agent.sidecar.recording_clients import RecordingLLMClient, ReplayLLMClient


@dataclass
class FixtureRule:
    match_tool: str
    match_args_contain: dict | None
    response: dict


@dataclass
class EvalCase:
    name: str
    description: str
    intent: str
    clarify_responses: list[str]
    fixture_observations: list[FixtureRule]
    expected_calls: list[Any]
    allow_extra_calls: bool
    terminal_action: str
    max_steps: int
    # If set, bypass live/record/replay and use these LLM responses in order.
    # Used by cases that need to deliberately inject malformed assistant output
    # to verify the agent's parse-error / recovery paths.
    scripted_llm_responses: list[dict] | None = None


def load_case(path: Path) -> EvalCase:
    data = json.loads(path.read_text(encoding="utf-8"))
    return EvalCase(
        name=data["name"],
        description=data.get("description", ""),
        intent=data["intent"],
        clarify_responses=data.get("clarify_responses", []),
        fixture_observations=[
            FixtureRule(
                match_tool=f["match_tool"],
                match_args_contain=f.get("match_args_contain"),
                response=f["response"],
            ) for f in data.get("fixture_observations", [])
        ],
        expected_calls=data.get("expected_calls", []),
        allow_extra_calls=data.get("allow_extra_calls", True),
        terminal_action=data.get("terminal_action", "finish"),
        max_steps=data.get("max_steps", 20),
        scripted_llm_responses=data.get("scripted_llm_responses"),
    )


class ScriptedLLMClient:
    """Returns scripted responses in order. Used by cases with scripted_llm_responses."""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)

    async def generate_structured(self, messages, json_schema, *, model,
                                  temperature: float = 0.0, timeout_s: float = 120.0) -> dict:
        if not self._responses:
            raise RuntimeError("scripted LLM exhausted")
        return self._responses.pop(0)


class MockMayaClient:
    """Records tool calls; returns fixture responses; queues clarify responses."""
    def __init__(self, fixtures: list[FixtureRule], clarify_responses: list[str]) -> None:
        self.fixtures = fixtures
        self.clarify_pending = list(clarify_responses)
        self.recorded_calls: list[tuple[str, dict]] = []
        self.events: list[dict] = []
        self._loop_ref: AgentLoop | None = None

    def attach_loop(self, loop: AgentLoop) -> None:
        self._loop_ref = loop

    async def call_tool(self, intent_id: str, call_id: str, tool: str, args: dict) -> dict:
        self.recorded_calls.append((tool, args))
        for rule in self.fixtures:
            if rule.match_tool != tool:
                continue
            if rule.match_args_contain:
                if not all(args.get(k) == v for k, v in rule.match_args_contain.items()):
                    continue
            return rule.response
        return {"ok": False, "error": f"no fixture defined for {tool}"}

    async def emit(self, event: dict) -> None:
        self.events.append(event)
        if event.get("type") == "clarify_question" and self._loop_ref:
            if self.clarify_pending:
                response = self.clarify_pending.pop(0)
                await self._loop_ref.provide_clarify_response(event["intent_id"], response)


def build_llm_client(*, mode: str, case_name: str, recordings_dir: Path,
                    real_factory) -> LLMClient:
    rec_path = recordings_dir / f"{case_name}.jsonl"
    if mode == "replay":
        return ReplayLLMClient(rec_path)
    if mode == "record":
        return RecordingLLMClient(real_factory(), rec_path)
    if mode == "live":
        return real_factory()
    if mode == "auto":
        if rec_path.exists():
            return ReplayLLMClient(rec_path)
        return real_factory()
    raise ValueError(f"Unknown mode: {mode}")


def get_eval_mode() -> str:
    return os.environ.get("MAYA_AGENT_EVAL_MODE", "auto")
