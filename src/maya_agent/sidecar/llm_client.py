"""LLM client abstraction. The agent loop talks to LLMClient, never to a concrete
implementation. This lets us swap Ollama for vLLM / OpenAI-compatible / etc.
"""
from __future__ import annotations

from typing import Literal, Protocol
from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMClient(Protocol):
    async def generate_structured(
        self,
        messages: list[ChatMessage],
        json_schema: dict,
        *,
        model: str,
        temperature: float = 0.0,
        timeout_s: float = 120.0,
    ) -> dict:
        """Call the LLM and return a parsed JSON object conforming to json_schema.

        Raises LLMError on transport / timeout / schema-violation failures.
        """
        ...


class LLMError(Exception):
    """Raised by LLMClient implementations on failure."""
