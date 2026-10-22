"""Ephemeral sticky routing for one Responses turn, never shared across turns."""

from __future__ import annotations

from collections.abc import Mapping
from threading import Lock
from typing import Any, Optional

TURN_STATE_HEADER = "x-codex-turn-state"


def header_value(headers: Any, name: str, default=None) -> Any:
    if not isinstance(headers, Mapping):
        return default
    return next((value for key, value in headers.items() if key.lower() == name), default)


class ResponsesTurnState:
    def __init__(self) -> None:
        self._lock = Lock()
        self._identity = None
        self._value = None
        self._epoch = 0
        self._closed = False

    def prepare(self, identity: tuple) -> tuple[int, Optional[str]]:
        with self._lock:
            if self._closed:
                raise RuntimeError("Responses turn is closed.")
            if self._identity != identity:
                self._identity, self._value = identity, None
                self._epoch += 1
            return self._epoch, self._value

    def capture(self, epoch: int, value: Any) -> None:
        if not isinstance(value, str) or not value or "\r" in value or "\n" in value:
            return
        with self._lock:
            if not self._closed and self._epoch == epoch and self._value is None:
                self._value = value

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._identity = self._value = None
