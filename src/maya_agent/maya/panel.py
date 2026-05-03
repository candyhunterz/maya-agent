"""Maya Agent Qt panel. Dockable widget with chat, input, status, controls.

Imports through qtpy so the panel works under whatever Qt binding mayapy
ships (PySide2 on Maya 2024, PySide6 on Maya 2025+). Tested manually inside
Maya. The panel owns:
- A CommandServer instance
- A subprocess.Popen reference for the sidecar (if launched in-panel)
- A chat model (list of items: user message, assistant message, tool entry)
- A ToolDispatcher hooked to the ToolRegistry
"""
from __future__ import annotations

import logging
import os
import secrets
import stat
import subprocess
import sys
import uuid
from pathlib import Path

from qtpy import QtCore, QtGui, QtWidgets

from maya_agent.core.protocol import (
    AssistantMessage, CancelMessage, ClarifyQuestionMessage, ClarifyResponseMessage,
    IntentFailedMessage, IntentFinishedMessage, ThinkingMessage, ToolCallMessage,
    ToolInventoryMessage, ToolResultMessage, UserIntentMessage,
)
from maya_agent.core.registry import ToolRegistry
from maya_agent.maya.command_server import CommandServer
from maya_agent.maya.tool_dispatcher import ToolDispatcher

_log = logging.getLogger(__name__)


class _ChatItem(QtWidgets.QFrame):
    """Base for items rendered in the chat list."""


class _MessageItem(_ChatItem):
    def __init__(self, role: str, text: str) -> None:
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel(f"<b>{role}:</b> {text}")
        label.setWordWrap(True)
        layout.addWidget(label)


class _ToolEntry(_ChatItem):
    """Inline collapsible tool-call entry."""
    def __init__(self, tool: str, args: dict) -> None:
        super().__init__()
        self._args = args
        self._result: dict | None = None
        layout = QtWidgets.QVBoxLayout(self)
        self._header = QtWidgets.QLabel(f"⟳ {tool}")
        self._header.setStyleSheet("color: #888; font-family: monospace;")
        layout.addWidget(self._header)
        self._tool = tool

    def mark_finished(self, ok: bool, value, error: str | None) -> None:
        self._result = {"ok": ok, "value": value, "error": error}
        icon = "✓" if ok else "✗"
        self._header.setText(f"{icon} {self._tool}")


def _write_session_token() -> tuple[str, Path]:
    """Generate a 32-byte URL-safe token, write to ~/.maya-agent/session-<pid>.token
    with 0600 permissions, return (token, file_path)."""
    token = secrets.token_urlsafe(32)
    token_dir = Path.home() / ".maya-agent"
    token_dir.mkdir(parents=True, exist_ok=True)
    path = token_dir / f"session-{os.getpid()}.token"
    path.write_text(token, encoding="utf-8")
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600 — owner read/write only
    except OSError:
        # Windows: chmod has limited effect; ACL enforcement is via file location in user profile
        pass
    return token, path


class MayaAgentPanel(QtWidgets.QWidget):
    def __init__(self, registry: ToolRegistry, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._registry = registry
        self._dispatcher = ToolDispatcher(registry)
        self._session_token, self._token_file = _write_session_token()
        self._server = CommandServer(expected_session_token=self._session_token)
        self._sidecar_process: subprocess.Popen | None = None
        self._tool_entries: dict[str, _ToolEntry] = {}  # call_id -> entry
        self._current_intent_id: str | None = None
        # Outer undo chunks per active intent. Maya supports nested chunks; we
        # open one outer chunk per intent so a single Ctrl+Z reverts the whole
        # agentic action (each tool's mutating wrapper opens its own inner chunk).
        self._intent_chunks_open: set[str] = set()

        self._build_ui()
        self._wire_signals()
        self._server.start()
        self._update_status_disconnected()

    def _build_ui(self) -> None:
        v = QtWidgets.QVBoxLayout(self)

        # Status row
        self._status_label = QtWidgets.QLabel("● Disconnected")
        self._status_label.setStyleSheet("padding: 4px;")
        v.addWidget(self._status_label)

        # Plugin warning banner (hidden by default)
        self._warning_banner = QtWidgets.QLabel("")
        self._warning_banner.setStyleSheet(
            "background: #5a3a00; color: white; padding: 6px;")
        self._warning_banner.hide()
        v.addWidget(self._warning_banner)

        # Chat area
        self._chat = QtWidgets.QListWidget()
        v.addWidget(self._chat, stretch=1)

        # Input area
        self._input = QtWidgets.QPlainTextEdit()
        self._input.setPlaceholderText("Type a request... (Ctrl+Enter to send)")
        self._input.setMaximumHeight(80)
        v.addWidget(self._input)

        # Buttons
        h = QtWidgets.QHBoxLayout()
        self._send_btn = QtWidgets.QPushButton("Send")
        self._undo_btn = QtWidgets.QPushButton("Undo last")
        self._clear_btn = QtWidgets.QPushButton("Clear chat")
        self._stop_btn = QtWidgets.QPushButton("■ Stop")
        self._stop_btn.hide()
        h.addWidget(self._send_btn)
        h.addWidget(self._undo_btn)
        h.addWidget(self._clear_btn)
        h.addWidget(self._stop_btn)
        h.addStretch()
        self._start_sidecar_btn = QtWidgets.QPushButton("Start agent")
        h.addWidget(self._start_sidecar_btn)
        v.addLayout(h)

    def _wire_signals(self) -> None:
        self._send_btn.clicked.connect(self._on_send_clicked)
        self._undo_btn.clicked.connect(self._on_undo_clicked)
        self._clear_btn.clicked.connect(self._on_clear_clicked)
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        self._start_sidecar_btn.clicked.connect(self._on_start_sidecar_clicked)

        self._server.client_connected.connect(self._on_client_connected)
        self._server.client_disconnected.connect(self._on_client_disconnected)
        self._server.message_received.connect(self._on_message_received)

        # Ctrl+Enter to send
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+Return"), self).activated.connect(
            self._on_send_clicked)

    # --- UI handlers ---

    def _on_send_clicked(self) -> None:
        text = self._input.toPlainText().strip()
        if not text or not self._server.is_connected():
            return
        intent_id = str(uuid.uuid4())
        self._current_intent_id = intent_id
        self._open_intent_chunk(intent_id, text)
        self._add_chat(_MessageItem("User", text))
        self._input.clear()
        self._stop_btn.show()
        self._server.send_message(UserIntentMessage(intent_id=intent_id, text=text))

    def _open_intent_chunk(self, intent_id: str, intent_text: str) -> None:
        """Open an outer undo chunk for the whole intent. One Ctrl+Z reverts the
        entire agentic action regardless of how many mutating tools ran inside."""
        try:
            from maya import cmds
            short = intent_text.replace("\n", " ")[:50]
            cmds.undoInfo(openChunk=True, chunkName=f"agent: {short}")
            self._intent_chunks_open.add(intent_id)
        except Exception:
            _log.exception("Failed to open intent undo chunk for %s", intent_id)

    def _close_intent_chunk(self, intent_id: str) -> None:
        if intent_id not in self._intent_chunks_open:
            return
        try:
            from maya import cmds
            cmds.undoInfo(closeChunk=True)
        except Exception:
            _log.exception("Failed to close intent undo chunk for %s", intent_id)
        finally:
            self._intent_chunks_open.discard(intent_id)

    def _on_undo_clicked(self) -> None:
        try:
            from maya import cmds
            cmds.undo()
        except Exception:
            _log.exception("Undo failed")

    def _on_clear_clicked(self) -> None:
        if QtWidgets.QMessageBox.question(
            self, "Clear chat", "Clear conversation history and cross-intent memory?"
        ) == QtWidgets.QMessageBox.Yes:
            self._chat.clear()
            self._tool_entries.clear()

    def _on_stop_clicked(self) -> None:
        if self._current_intent_id:
            self._server.send_message(CancelMessage(intent_id=self._current_intent_id))

    def _on_start_sidecar_clicked(self) -> None:
        if self._sidecar_process and self._sidecar_process.poll() is None:
            return
        log_dir = Path.home() / ".maya-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"sidecar-{os.getpid()}.log"
        env = os.environ.copy()
        cmd = [
            sys.executable, "-m", "maya_agent.sidecar",
            "--pipe", self._server.full_pipe_path(),
            "--session-token-file", str(self._token_file),
            "--log-file", str(log_file),
        ]
        if env.get("MAYA_AGENT_MODEL"):
            cmd += ["--model", env["MAYA_AGENT_MODEL"]]
        self._sidecar_process = subprocess.Popen(cmd, env=env)
        _log.info("Spawned sidecar PID %d, logs at %s", self._sidecar_process.pid, log_file)

    # --- Server signals ---

    def _on_client_connected(self) -> None:
        self._status_label.setText("● Connected — sending inventory")
        self._status_label.setStyleSheet("color: #2c2; padding: 4px;")
        # Send the inventory
        self._server.send_message(ToolInventoryMessage(tools=self._registry.inventory()))

    def _on_client_disconnected(self) -> None:
        self._update_status_disconnected()

    def _update_status_disconnected(self) -> None:
        self._status_label.setText(
            f"● Disconnected — pipe: {self._server.full_pipe_path()} | "
            f"token-file: {self._token_file}"
        )
        self._status_label.setStyleSheet("color: #888; padding: 4px;")
        self._stop_btn.hide()

    def _on_message_received(self, msg) -> None:
        if isinstance(msg, ToolCallMessage):
            entry = _ToolEntry(msg.tool, msg.args)
            self._tool_entries[msg.call_id] = entry
            self._add_chat(entry)
            # Dispatch on this thread (we're already on the main thread via Qt queued connection)
            result = self._dispatcher.dispatch(msg.tool, msg.args)
            entry.mark_finished(result.ok, result.value, result.error)
            self._server.send_message(ToolResultMessage(
                intent_id=msg.intent_id, call_id=msg.call_id,
                ok=result.ok, value=result.value, error=result.error,
            ))
        elif isinstance(msg, AssistantMessage):
            self._add_chat(_MessageItem("Agent", msg.text))
        elif isinstance(msg, ClarifyQuestionMessage):
            self._add_chat(_MessageItem("Agent (?)", msg.text))
            # Next user input becomes a clarify_response
            self._send_btn.clicked.disconnect()
            self._send_btn.clicked.connect(lambda: self._send_clarify_response(msg.intent_id))
        elif isinstance(msg, IntentFinishedMessage):
            self._add_chat(_MessageItem("Agent", msg.user_message))
            self._close_intent_chunk(msg.intent_id)
            self._stop_btn.hide()
            self._current_intent_id = None
        elif isinstance(msg, IntentFailedMessage):
            self._add_chat(_MessageItem("Agent (failed)", msg.error))
            self._close_intent_chunk(msg.intent_id)
            self._stop_btn.hide()
            self._current_intent_id = None
        elif isinstance(msg, ThinkingMessage):
            # Logged but not rendered by default
            _log.debug("[thinking %s] %s", msg.intent_id, msg.text)

    def _send_clarify_response(self, intent_id: str) -> None:
        text = self._input.toPlainText().strip()
        if not text:
            return
        self._add_chat(_MessageItem("User", text))
        self._input.clear()
        self._server.send_message(ClarifyResponseMessage(intent_id=intent_id, text=text))
        # Restore normal Send wiring
        self._send_btn.clicked.disconnect()
        self._send_btn.clicked.connect(self._on_send_clicked)

    def _add_chat(self, widget: _ChatItem) -> None:
        item = QtWidgets.QListWidgetItem()
        item.setSizeHint(widget.sizeHint())
        self._chat.addItem(item)
        self._chat.setItemWidget(item, widget)
        self._chat.scrollToBottom()

    def show_plugin_warnings(self, warnings: list[str]) -> None:
        if not warnings:
            self._warning_banner.hide()
            return
        self._warning_banner.setText(
            f"⚠ {len(warnings)} plugin issue(s): " + "; ".join(warnings[:3])
        )
        self._warning_banner.show()
