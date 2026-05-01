"""QLocalServer that accepts the sidecar connection and exchanges length-prefixed
JSON frames. Inbound frames are emitted as Qt signals on the main thread.

Auth: incoming connections must send an AuthMessage with the expected session
token before any other message. client_connected emits only after auth succeeds;
on auth failure the socket is dropped silently.
"""
from __future__ import annotations

import hmac
import logging
import os
from typing import Callable

from PySide6 import QtCore, QtNetwork

from maya_agent.core.frames import FrameDecoder, FrameError, encode_frame
from maya_agent.core.protocol import AuthMessage, Message, encode_message, parse_message

_log = logging.getLogger(__name__)


def default_pipe_path() -> str:
    """Pipe path that includes the current PID so multiple Maya instances don't collide."""
    if os.name == "nt":
        return f"maya-agent-{os.getpid()}"  # QLocalServer prepends \\.\pipe\ on Windows
    return f"/tmp/maya-agent-{os.getpid()}.sock"


class CommandServer(QtCore.QObject):
    """Owns a QLocalServer + a single client socket (the sidecar).

    Emits message_received(Message) for messages received AFTER successful auth.
    Send messages via send_message() — works whether or not the client is connected
    (queued and flushed after auth succeeds, never before).
    """

    message_received = QtCore.Signal(object)  # Message instance
    client_connected = QtCore.Signal()         # emitted only after auth success
    client_disconnected = QtCore.Signal()

    def __init__(
        self,
        expected_session_token: str,
        pipe_name: str | None = None,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if not expected_session_token:
            raise ValueError("expected_session_token must be a non-empty string")
        self._expected_token = expected_session_token
        self._pipe_name = pipe_name or default_pipe_path()
        self._server = QtNetwork.QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        self._socket: QtNetwork.QLocalSocket | None = None
        self._authed: bool = False
        self._decoder = FrameDecoder()
        self._send_queue: list[bytes] = []

    def start(self) -> None:
        QtNetwork.QLocalServer.removeServer(self._pipe_name)
        if not self._server.listen(self._pipe_name):
            raise RuntimeError(
                f"Failed to listen on {self._pipe_name}: {self._server.errorString()}"
            )
        _log.info("CommandServer listening on %s", self.full_pipe_path())

    def stop(self) -> None:
        if self._socket is not None:
            self._socket.disconnectFromServer()
            self._socket = None
        self._server.close()

    def full_pipe_path(self) -> str:
        if os.name == "nt":
            return rf"\\.\pipe\{self._pipe_name}"
        return self._pipe_name

    def is_connected(self) -> bool:
        return (
            self._socket is not None
            and self._authed
            and self._socket.state() == QtNetwork.QLocalSocket.ConnectedState
        )

    def send_message(self, msg: Message) -> None:
        frame = encode_frame(encode_message(msg))
        if self.is_connected():
            self._socket.write(frame)
            self._socket.flush()
        else:
            # Queue messages from the panel — flushed only after auth succeeds.
            self._send_queue.append(frame)

    def _on_new_connection(self) -> None:
        if self._socket is not None:
            extra = self._server.nextPendingConnection()
            extra.disconnectFromServer()
            return
        self._socket = self._server.nextPendingConnection()
        self._authed = False
        self._decoder = FrameDecoder()
        self._socket.readyRead.connect(self._on_ready_read)
        self._socket.disconnected.connect(self._on_disconnected)
        _log.info("Sidecar client connected (awaiting auth)")

    def _on_ready_read(self) -> None:
        if self._socket is None:
            return
        data = bytes(self._socket.readAll().data())
        try:
            for raw in self._decoder.feed(data):
                try:
                    msg = parse_message(raw)
                except Exception:
                    _log.exception("Invalid incoming message")
                    continue
                if not self._authed:
                    self._handle_auth(msg)
                    continue
                self.message_received.emit(msg)
        except FrameError:
            _log.exception("Frame decode error; closing socket")
            self._socket.disconnectFromServer()

    def _handle_auth(self, msg: Message) -> None:
        """Validate the first message. Must be AuthMessage with the expected token."""
        if not isinstance(msg, AuthMessage):
            # Don't log the offered content — could leak. Just close.
            _log.warning("First message was not auth; closing connection")
            self._socket.disconnectFromServer()
            return
        if not hmac.compare_digest(msg.session_token, self._expected_token):
            _log.warning("Auth failed (token mismatch); closing connection")
            self._socket.disconnectFromServer()
            return
        self._authed = True
        # Flush queued outbound frames now that we're authenticated
        for frame in self._send_queue:
            self._socket.write(frame)
        self._socket.flush()
        self._send_queue.clear()
        _log.info("Auth succeeded; sidecar fully connected")
        self.client_connected.emit()

    def _on_disconnected(self) -> None:
        was_authed = self._authed
        self._socket = None
        self._authed = False
        if was_authed:
            _log.info("Sidecar client disconnected")
            self.client_disconnected.emit()
        else:
            _log.info("Pre-auth client disconnected")
