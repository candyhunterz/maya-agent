import asyncio
import pytest
from maya_agent.sidecar.agent_loop import AgentLoop, IntentRequest
from maya_agent.sidecar.llm_client import ChatMessage


class _ScriptedLLM:
    """Returns the next scripted response on each call. Records messages it received."""
    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.calls: list[list[ChatMessage]] = []
    async def generate_structured(self, messages, json_schema, *, model,
                                  temperature=0.0, timeout_s=120.0):
        self.calls.append(list(messages))
        if not self._responses:
            raise RuntimeError("scripted LLM exhausted")
        return self._responses.pop(0)


class _MockMaya:
    """Mock MayaClient that returns scripted tool results."""
    def __init__(self, results: dict[str, dict]) -> None:
        self.results = results  # tool_name -> result dict
        self.tool_calls: list[tuple[str, dict]] = []
        self.events_sent: list[dict] = []
    async def call_tool(self, intent_id, call_id, tool, args):
        self.tool_calls.append((tool, args))
        return self.results.get(tool, {"ok": False, "error": f"no fixture for {tool}"})
    async def emit(self, event: dict):
        self.events_sent.append(event)


_INV = [
    {"name": "inspect_scene", "description": "Inspect.", "mutating": False,
     "json_schema": {"type": "object", "properties": {}}},
    {"name": "fix_euler", "description": "Fix euler.", "mutating": True,
     "json_schema": {"type": "object", "properties": {"obj": {"type": "string"}}, "required": ["obj"]}},
]


@pytest.mark.asyncio
async def test_happy_path_two_tools_then_finish():
    llm = _ScriptedLLM([
        {"thinking": "first inspect", "action": "tool_call", "tool": "inspect_scene", "arguments": {}},
        {"thinking": "now fix",       "action": "tool_call", "tool": "fix_euler",     "arguments": {"obj": "ctrl"}},
        {"thinking": "done",          "action": "finish", "user_message": "Done.", "summary": "Fixed euler on ctrl."},
    ])
    maya = _MockMaya({
        "inspect_scene": {"ok": True, "value": {"selection": ["ctrl"]}},
        "fix_euler":     {"ok": True, "value": {"fixed": 1}},
    })
    loop = AgentLoop(llm=llm, maya=maya, inventory=_INV, model="m", max_steps=10)
    result = await loop.run_intent(IntentRequest(intent_id="i", text="fix euler"),
                                    on_event=lambda e: None)
    assert result.terminal_action == "finish"
    assert result.summary == "Fixed euler on ctrl."
    assert result.user_message == "Done."
    assert [tc[0] for tc in maya.tool_calls] == ["inspect_scene", "fix_euler"]


@pytest.mark.asyncio
async def test_unknown_tool_returns_error_observation():
    llm = _ScriptedLLM([
        {"thinking": "try fake", "action": "tool_call", "tool": "nonexistent", "arguments": {}},
        {"thinking": "ok finish", "action": "finish", "user_message": "Couldn't.", "summary": "No tool."},
    ])
    maya = _MockMaya({})
    loop = AgentLoop(llm=llm, maya=maya, inventory=_INV, model="m", max_steps=10)
    result = await loop.run_intent(IntentRequest(intent_id="i", text="x"),
                                    on_event=lambda e: None)
    # Last user message in the LLM call history should describe the unknown tool error
    last_user_content = [m.content for m in llm.calls[-1] if m.role == "user"][-1]
    assert "Unknown tool" in last_user_content


@pytest.mark.asyncio
async def test_invalid_arguments_loop_back_as_error():
    llm = _ScriptedLLM([
        {"thinking": "wrong args", "action": "tool_call", "tool": "fix_euler", "arguments": {}},  # missing 'obj'
        {"thinking": "retry",      "action": "tool_call", "tool": "fix_euler", "arguments": {"obj": "ctrl"}},
        {"thinking": "done",       "action": "finish", "user_message": "k", "summary": "k"},
    ])
    maya = _MockMaya({"fix_euler": {"ok": True, "value": {"fixed": 1}}})
    loop = AgentLoop(llm=llm, maya=maya, inventory=_INV, model="m", max_steps=10)
    result = await loop.run_intent(IntentRequest(intent_id="i", text="fix"),
                                    on_event=lambda e: None)
    # First call to maya should NOT have happened (validation rejected before dispatch)
    assert maya.tool_calls == [("fix_euler", {"obj": "ctrl"})]
    assert result.terminal_action == "finish"


@pytest.mark.asyncio
async def test_clarify_then_continue():
    events: list[dict] = []
    llm = _ScriptedLLM([
        {"thinking": "ambiguous", "action": "clarify", "question": "Which arm?"},
        {"thinking": "now act",   "action": "tool_call", "tool": "fix_euler", "arguments": {"obj": "L_arm"}},
        {"thinking": "done",      "action": "finish", "user_message": "Fixed.", "summary": "."},
    ])
    maya = _MockMaya({"fix_euler": {"ok": True, "value": {"fixed": 1}}})
    loop = AgentLoop(llm=llm, maya=maya, inventory=_INV, model="m",
                     max_steps=10, max_clarifies=3)

    # Inject a clarify response via the loop's clarify queue
    async def feed_response():
        await asyncio.sleep(0.05)
        await loop.provide_clarify_response("i", "L arm please")
    asyncio.create_task(feed_response())

    result = await loop.run_intent(IntentRequest(intent_id="i", text="fix arm"),
                                    on_event=lambda e: events.append(e))
    assert result.terminal_action == "finish"
    # Last user message before final tool call should contain the clarification text
    msgs_before_final = llm.calls[1]
    assert any("L arm please" in m.content for m in msgs_before_final if m.role == "user")


@pytest.mark.asyncio
async def test_step_limit_forces_finish():
    # LLM keeps calling inspect_scene forever
    llm = _ScriptedLLM([
        {"thinking": ".", "action": "tool_call", "tool": "inspect_scene", "arguments": {}}
        for _ in range(5)
    ] + [
        {"thinking": "done", "action": "finish", "user_message": "Stopped.", "summary": "Hit limit."}
    ])
    maya = _MockMaya({"inspect_scene": {"ok": True, "value": {}}})
    loop = AgentLoop(llm=llm, maya=maya, inventory=_INV, model="m", max_steps=4)
    result = await loop.run_intent(IntentRequest(intent_id="i", text="loop"),
                                    on_event=lambda e: None)
    # Either finished naturally on the warning, or we forced a finish
    assert result.terminal_action in ("finish", "step_limit")
    assert len(maya.tool_calls) <= 4
