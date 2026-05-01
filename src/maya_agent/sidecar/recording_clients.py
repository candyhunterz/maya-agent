"""Recording and replay wrappers for the LLMClient.

RecordingLLMClient wraps any LLMClient and writes (request, response) pairs to JSONL.
ReplayLLMClient reads JSONL and returns the recorded response by request hash.
Used by the eval harness to keep CI deterministic.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from maya_agent.sidecar.llm_client import ChatMessage, LLMClient, LLMError


def request_hash(messages: list[Any], json_schema: dict, model: str) -> str:
    """Stable hash of the LLM request for matching live and replayed calls."""
    if messages and hasattr(messages[0], "model_dump"):
        messages = [m.model_dump() for m in messages]
    payload = json.dumps(
        {"messages": messages, "schema": json_schema, "model": model},
        sort_keys=True, separators=(", ", ": "),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class RecordingLLMClient:
    """Wraps a real LLMClient, appending (hash, request, response) to JSONL on each call."""

    def __init__(self, inner: LLMClient, recording_path: Path) -> None:
        self._inner = inner
        self._path = Path(recording_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    async def generate_structured(self, messages, json_schema, *, model,
                                  temperature: float = 0.0, timeout_s: float = 120.0) -> dict:
        response = await self._inner.generate_structured(
            messages, json_schema, model=model,
            temperature=temperature, timeout_s=timeout_s,
        )
        h = request_hash(messages, json_schema, model)
        record = {
            "request_hash": h,
            "request": {
                "messages": [m.model_dump() if hasattr(m, "model_dump") else m for m in messages],
                "schema": json_schema,
                "model": model,
            },
            "response": response,
        }
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        return response


class ReplayLLMClient:
    """Reads JSONL and replays recorded responses. Raises on cache miss."""

    def __init__(self, recording_path: Path) -> None:
        self._path = Path(recording_path)
        self._cache: dict[str, dict] = {}
        if self._path.exists():
            for line in self._path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                self._cache[rec["request_hash"]] = rec["response"]

    async def generate_structured(self, messages, json_schema, *, model,
                                  temperature: float = 0.0, timeout_s: float = 120.0) -> dict:
        h = request_hash(messages, json_schema, model)
        if h not in self._cache:
            raise LLMError(f"no recording for request hash {h[:12]}... in {self._path}")
        return self._cache[h]
