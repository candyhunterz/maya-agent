import asyncio
from pathlib import Path

import pytest

from maya_agent.sidecar.agent_loop import AgentLoop, IntentRequest
from maya_agent.sidecar.ollama_client import OllamaClient

from tests.eval.runner import (
    load_case, MockMayaClient, ScriptedLLMClient, build_llm_client, get_eval_mode,
)
from tests.eval.matchers import assert_calls_match

CASES_DIR = Path(__file__).parent / "cases"
RECORDINGS_DIR = Path(__file__).parent / "recordings"

# Static inventory used during eval. Mirrors the 5 framework example tools.
EVAL_INVENTORY = [
    {"name": "inspect_scene", "description": "Inspect scene.", "mutating": False,
     "json_schema": {"type": "object", "properties": {"deep": {"type": "boolean", "default": False}}}},
    {"name": "query_animation_curves", "description": "Query anim curves.", "mutating": False,
     "json_schema": {"type": "object",
                     "properties": {"objects": {"type": "array", "items": {"type": "string"}},
                                    "attributes": {"type": ["array", "null"]}},
                     "required": ["objects"]}},
    {"name": "find_euler_discontinuities", "description": "Find Euler jumps.", "mutating": False,
     "json_schema": {"type": "object",
                     "properties": {"objects": {"type": "array", "items": {"type": "string"}},
                                    "threshold_degrees": {"type": "number", "default": 180.0}},
                     "required": ["objects"]}},
    {"name": "fix_euler_discontinuities", "description": "Fix Euler jumps.", "mutating": True,
     "json_schema": {"type": "object",
                     "properties": {"objects": {"type": "array", "items": {"type": "string"}}},
                     "required": ["objects"]}},
    {"name": "playblast", "description": "Render playblast.", "mutating": False,
     "json_schema": {"type": "object",
                     "properties": {"output_path": {"type": "string"},
                                    "start_frame": {"type": ["number", "null"]},
                                    "end_frame": {"type": ["number", "null"]},
                                    "width": {"type": "integer", "default": 1280},
                                    "height": {"type": "integer", "default": 720}},
                     "required": ["output_path"]}},
]


def _real_llm_factory():
    return OllamaClient()


@pytest.mark.parametrize("case_path", sorted(CASES_DIR.glob("*.json")))
def test_eval_case(case_path):
    case = load_case(case_path)
    if case.scripted_llm_responses is not None:
        # Bypass live/record/replay — case has scripted LLM responses
        llm = ScriptedLLMClient(case.scripted_llm_responses)
    else:
        mode = get_eval_mode()
        rec_path = RECORDINGS_DIR / f"{case.name}.jsonl"
        # PRD Definition-of-done #3 wants `pytest tests/eval -q` to either pass
        # (recordings present) or skip cleanly. Without a recording and without
        # Ollama running, the live fallback would error mid-test — skip instead.
        if mode in ("auto", "replay") and not rec_path.exists():
            pytest.skip(
                f"No recording at {rec_path}. Run with MAYA_AGENT_EVAL_MODE=record "
                f"against live Ollama to generate one."
            )
        llm = build_llm_client(
            mode=mode, case_name=case.name,
            recordings_dir=RECORDINGS_DIR, real_factory=_real_llm_factory,
        )
    maya = MockMayaClient(case.fixture_observations, case.clarify_responses)
    loop = AgentLoop(
        llm=llm, maya=maya, inventory=EVAL_INVENTORY,
        model="gemma3:27b", max_steps=case.max_steps,
    )
    maya.attach_loop(loop)
    result = asyncio.run(loop.run_intent(
        IntentRequest(intent_id="t", text=case.intent),
        on_event=lambda e: asyncio.create_task(maya.emit(e)),
    ))
    assert_calls_match(maya.recorded_calls, case.expected_calls,
                       allow_extra=case.allow_extra_calls)
    assert result.terminal_action == case.terminal_action, (
        f"expected {case.terminal_action}, got {result.terminal_action}"
    )
