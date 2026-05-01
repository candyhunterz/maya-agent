"""MayaClient: async socket client that speaks length-prefixed JSON frames.

Connects either to a TCP loopback (for tests) or a named pipe / unix domain
socket (production). Sends/receives Message instances from the protocol module.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from maya_agent.core.frames import encode_frame, FrameDecoder
from maya_agent.core.protocol import Message, encode_message, parse_message

_log = logging.getLogger(__name__)


class MayaClient:
    def __init__(self) -> None:
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._decoder = FrameDecoder()
        self._inbox: asyncio.Queue[Message] = asyncio.Queue()
        self._reader_task: asyncio.Task | None = None

    async def connect_pipe(self, pipe_path: str) -> None:
        """Connect to a named pipe (Windows) or unix domain socket (Linux/macOS)."""
        if sys.platform == "win32":
            # Windows named pipe via asyncio
            from asyncio.windows_events import _WindowsSelectorEventLoopPolicy  # noqa
            # asyncio doesn't have a built-in connect_pipe; we fall back to a thread
            # implementation if needed. For now, this is a stub raising NotImplementedError
            # — wired up in Phase 7 alongside the sidecar entry point.
            raise NotImplementedError("Windows named-pipe connect: implemented in Phase 7")
        else:
            self._reader, self._writer = await asyncio.open_unix_connection(pipe_path)
        self._start_reader()

    async def connect_tcp(self, host: str, port: int) -> None:
        """Useful for tests."""
        self._reader, self._writer = await asyncio.open_connection(host, port)
        self._start_reader()

    def _start_reader(self) -> None:
        self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        assert self._reader is not None
        try:
            while True:
                chunk = await self._reader.read(65536)
                if not chunk:
                    return
                for raw in self._decoder.feed(chunk):
                    try:
                        msg = parse_message(raw)
                    except Exception as e:
                        _log.exception("Failed to parse incoming message: %s", e)
                        continue
                    await self._inbox.put(msg)
        except asyncio.CancelledError:
            raise
        except Exception:
            _log.exception("MayaClient read loop crashed")

    async def send(self, msg: Message) -> None:
        if self._writer is None:
            raise RuntimeError("MayaClient not connected")
        self._writer.write(encode_frame(encode_message(msg)))
        await self._writer.drain()

    async def receive(self) -> Message:
        return await self._inbox.get()

    async def close(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
