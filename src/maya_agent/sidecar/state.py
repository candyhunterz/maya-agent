"""Cross-intent memory: bounded ring of (intent_text, summary) pairs."""
from __future__ import annotations

from collections import deque


class CrossIntentMemory:
    def __init__(self, max_entries: int = 10) -> None:
        self._entries: deque[tuple[str, str]] = deque(maxlen=max_entries)

    def add(self, intent_text: str, summary: str) -> None:
        self._entries.append((intent_text, summary))

    def as_list(self) -> list[tuple[str, str]]:
        return list(self._entries)

    def clear(self) -> None:
        self._entries.clear()
