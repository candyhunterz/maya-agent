"""Wire protocol messages exchanged between Maya and the sidecar.

All messages are pydantic models with a `type` discriminator. Use parse_message()
to dispatch by type; encode_message() returns a JSON-serializable dict.
"""
from __future__ import annotations

from typing import Any, Literal, Union
from pydantic import BaseModel, Field, TypeAdapter


# Sidecar -> Maya/panel - must be the first message after connect
class AuthMessage(BaseModel):
    type: Literal["auth"] = "auth"
    session_token: str


# Maya/panel -> sidecar
class ToolInventoryMessage(BaseModel):
    type: Literal["tool_inventory"] = "tool_inventory"
    tools: list[dict]


class UserIntentMessage(BaseModel):
    type: Literal["user_intent"] = "user_intent"
    intent_id: str
    text: str


class ClarifyResponseMessage(BaseModel):
    type: Literal["clarify_response"] = "clarify_response"
    intent_id: str
    text: str


class CancelMessage(BaseModel):
    type: Literal["cancel"] = "cancel"
    intent_id: str


class ToolResultMessage(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    intent_id: str
    call_id: str
    ok: bool
    value: Any | None = None
    error: str | None = None


# Sidecar -> Maya/panel
class ToolCallMessage(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    intent_id: str
    call_id: str
    tool: str
    args: dict


class ThinkingMessage(BaseModel):
    type: Literal["thinking"] = "thinking"
    intent_id: str
    text: str


class AssistantMessage(BaseModel):
    type: Literal["assistant_message"] = "assistant_message"
    intent_id: str
    text: str


class ClarifyQuestionMessage(BaseModel):
    type: Literal["clarify_question"] = "clarify_question"
    intent_id: str
    text: str


class IntentFinishedMessage(BaseModel):
    type: Literal["intent_finished"] = "intent_finished"
    intent_id: str
    summary: str
    user_message: str


class IntentFailedMessage(BaseModel):
    type: Literal["intent_failed"] = "intent_failed"
    intent_id: str
    error: str


Message = Union[
    AuthMessage, ToolInventoryMessage, UserIntentMessage, ClarifyResponseMessage,
    CancelMessage, ToolResultMessage, ToolCallMessage, ThinkingMessage,
    AssistantMessage, ClarifyQuestionMessage, IntentFinishedMessage, IntentFailedMessage,
]

_adapter = TypeAdapter(Message, config={"discriminator": "type"})


def parse_message(data: dict) -> Message:
    """Parse a JSON-decoded dict into the appropriate Message subtype."""
    return _adapter.validate_python(data)


def encode_message(msg: Message) -> dict:
    """Encode a Message to a JSON-serializable dict."""
    return msg.model_dump()
