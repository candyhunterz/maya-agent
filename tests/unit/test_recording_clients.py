import json
from pathlib import Path
import pytest
from maya_agent.sidecar.llm_client import ChatMessage, LLMError
from maya_agent.sidecar.recording_clients import (
    RecordingLLMClient, ReplayLLMClient, request_hash,
)


class _FakeLLM:
    def __init__(self, response):
        self.response = response
        self.calls = []
    async def generate_structured(self, messages, json_schema, *, model, temperature=0.0, timeout_s=120.0):
        self.calls.append((messages, json_schema, model))
        return self.response


@pytest.mark.asyncio
async def test_recording_writes_jsonl(tmp_path):
    rec_file = tmp_path / "rec.jsonl"
    inner = _FakeLLM({"action": "finish", "thinking": "ok", "user_message": "done", "summary": "."})
    rec = RecordingLLMClient(inner, rec_file)
    msgs = [ChatMessage(role="user", content="hi")]
    schema = {"type": "object"}
    out = await rec.generate_structured(msgs, schema, model="m")
    assert out["action"] == "finish"
    lines = rec_file.read_text().strip().splitlines()
    assert len(lines) == 1
    rec_obj = json.loads(lines[0])
    assert "request_hash" in rec_obj
    assert rec_obj["response"]["action"] == "finish"


@pytest.mark.asyncio
async def test_replay_returns_recorded_response(tmp_path):
    rec_file = tmp_path / "rec.jsonl"
    inner = _FakeLLM({"action": "finish", "thinking": ".", "user_message": "x", "summary": "."})
    rec = RecordingLLMClient(inner, rec_file)
    msgs = [ChatMessage(role="user", content="hello")]
    schema = {"type": "object"}
    await rec.generate_structured(msgs, schema, model="m")

    replay = ReplayLLMClient(rec_file)
    out = await replay.generate_structured(msgs, schema, model="m")
    assert out["action"] == "finish"


@pytest.mark.asyncio
async def test_replay_raises_on_cache_miss(tmp_path):
    rec_file = tmp_path / "rec.jsonl"
    rec_file.write_text("")
    replay = ReplayLLMClient(rec_file)
    with pytest.raises(LLMError, match="no recording"):
        await replay.generate_structured(
            [ChatMessage(role="user", content="hi")], {"type": "object"}, model="m"
        )


def test_request_hash_is_deterministic_and_input_sensitive():
    a = request_hash([{"role": "user", "content": "a"}], {"x": 1}, "m")
    b = request_hash([{"role": "user", "content": "a"}], {"x": 1}, "m")
    c = request_hash([{"role": "user", "content": "b"}], {"x": 1}, "m")
    assert a == b
    assert a != c
