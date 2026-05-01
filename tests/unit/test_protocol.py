import pytest
from pydantic import ValidationError
from maya_agent.core.protocol import (
    AuthMessage, ToolInventoryMessage, UserIntentMessage, ClarifyResponseMessage,
    CancelMessage, ToolResultMessage, ToolCallMessage, ThinkingMessage,
    AssistantMessage, ClarifyQuestionMessage, IntentFinishedMessage,
    IntentFailedMessage, parse_message, encode_message,
)


def test_user_intent_round_trips():
    m = UserIntentMessage(intent_id="i1", text="hello")
    raw = encode_message(m)
    parsed = parse_message(raw)
    assert isinstance(parsed, UserIntentMessage)
    assert parsed.text == "hello"


def test_tool_call_carries_args_and_call_id():
    m = ToolCallMessage(intent_id="i1", call_id="c1", tool="inspect_scene", args={"x": 1})
    parsed = parse_message(encode_message(m))
    assert parsed.tool == "inspect_scene"
    assert parsed.args == {"x": 1}
    assert parsed.call_id == "c1"


def test_tool_result_with_error():
    m = ToolResultMessage(intent_id="i1", call_id="c1", ok=False, error="boom")
    parsed = parse_message(encode_message(m))
    assert parsed.ok is False
    assert parsed.error == "boom"
    assert parsed.value is None


def test_tool_inventory_round_trip():
    m = ToolInventoryMessage(tools=[
        {"name": "t", "description": "d", "json_schema": {}, "mutating": False}
    ])
    parsed = parse_message(encode_message(m))
    assert parsed.tools[0]["name"] == "t"


def test_parse_rejects_unknown_type():
    with pytest.raises(ValidationError):
        parse_message({"type": "nonsense", "intent_id": "i1"})


def test_parse_rejects_missing_required_field():
    with pytest.raises(ValidationError):
        parse_message({"type": "user_intent", "intent_id": "i1"})  # missing text


def test_auth_message_round_trips():
    m = AuthMessage(session_token="abc-123-def")
    parsed = parse_message(encode_message(m))
    assert isinstance(parsed, AuthMessage)
    assert parsed.session_token == "abc-123-def"
