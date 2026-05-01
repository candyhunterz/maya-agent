"""Length-prefixed JSON frame codec.

Each frame is a 4-byte big-endian unsigned integer (frame body length) followed
by `length` bytes of UTF-8 JSON. Trivially parseable; no escaping; supports
incremental decoding across socket chunk boundaries.
"""
from __future__ import annotations

import json
from typing import Iterator

DEFAULT_MAX_FRAME_BYTES = 16 * 1024 * 1024  # 16 MiB


class FrameError(Exception):
    """Raised when a frame cannot be decoded."""


def encode_frame(payload: dict) -> bytes:
    body = json.dumps(payload, separators=(", ", ": ")).encode("utf-8")
    return len(body).to_bytes(4, "big") + body


class FrameDecoder:
    """Stateful decoder. Feed bytes; iterate decoded JSON dicts."""

    def __init__(self, max_frame_bytes: int = DEFAULT_MAX_FRAME_BYTES) -> None:
        self._buf = bytearray()
        self._max = max_frame_bytes

    def feed(self, data: bytes) -> Iterator[dict]:
        self._buf.extend(data)
        while True:
            if len(self._buf) < 4:
                return
            length = int.from_bytes(self._buf[:4], "big")
            if length > self._max:
                raise FrameError(f"frame too large: {length} > {self._max}")
            if len(self._buf) < 4 + length:
                return
            body = bytes(self._buf[4 : 4 + length])
            del self._buf[: 4 + length]
            try:
                yield json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as e:
                raise FrameError(f"invalid JSON: {e}") from e
