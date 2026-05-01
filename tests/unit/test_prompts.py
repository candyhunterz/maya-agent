from maya_agent.sidecar.prompts import build_system_prompt, RESPONSE_SCHEMA


def test_system_prompt_includes_tool_inventory():
    inventory = [
        {"name": "inspect_scene", "description": "Look at the scene.", "mutating": False,
         "json_schema": {"type": "object", "properties": {"deep": {"type": "boolean"}}}},
        {"name": "fix_euler", "description": "Fix euler.", "mutating": True,
         "json_schema": {"type": "object", "properties": {"objs": {"type": "array"}}}},
    ]
    prompt = build_system_prompt(inventory, max_clarifies=3, summaries=[], current_intent="do X")
    assert "inspect_scene" in prompt
    assert "Look at the scene." in prompt
    assert "fix_euler" in prompt
    assert "do X" in prompt
    assert "clarify at most 3 times" in prompt.lower() or "at most 3" in prompt


def test_system_prompt_renders_summaries():
    inv = [{"name": "t", "description": "d", "mutating": False, "json_schema": {"type": "object"}}]
    summaries = [
        ("clean up arms", "Fixed 3 discontinuities on L_arm_FK_CTL."),
        ("playblast", "Rendered frames 1-100 at 720p."),
    ]
    prompt = build_system_prompt(inv, max_clarifies=3, summaries=summaries, current_intent="now legs")
    assert "clean up arms" in prompt
    assert "Fixed 3 discontinuities" in prompt
    assert "playblast" in prompt
    assert "now legs" in prompt


def test_response_schema_has_action_enum():
    assert RESPONSE_SCHEMA["properties"]["action"]["enum"] == ["tool_call", "clarify", "finish"]
    assert RESPONSE_SCHEMA["required"] == ["thinking", "action"]
