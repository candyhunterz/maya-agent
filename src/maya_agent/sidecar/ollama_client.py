"""OllamaClient: LLMClient implementation talking to Ollama HTTP API.

Uses the /api/chat endpoint with the `format` parameter set to a JSON schema
that constrains the response. Returns the parsed JSON object.
"""
from __future__ import annotations

import json
import logging

import httpx

from maya_agent.sidecar.llm_client import ChatMessage, LLMError

_log = logging.getLogger(__name__)


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self._base_url = base_url.rstrip("/")

    async def generate_structured(
        self,
        messages: list[ChatMessage],
        json_schema: dict,
        *,
        model: str,
        temperature: float = 0.0,
        timeout_s: float = 120.0,
    ) -> dict:
        payload = {
            "model": model,
            "messages": [m.model_dump() for m in messages],
            "format": json_schema,
            "stream": False,
            "options": {"temperature": temperature},
        }
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            try:
                resp = await client.post(f"{self._base_url}/api/chat", json=payload)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                raise LLMError(f"Ollama HTTP error: {e}") from e
        body = resp.json()
        content = body.get("message", {}).get("content")
        if not content:
            raise LLMError(f"Ollama response has no content: {body}")
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise LLMError(f"Ollama returned non-JSON content: {content[:200]}") from e
