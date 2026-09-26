from __future__ import annotations

import io
from collections.abc import Callable
from types import MappingProxyType
from typing import cast

import pytest


def _delete_no_progress_env(monkeypatch: pytest.MonkeyPatch, env_value: str | None) -> None:
    del env_value
    monkeypatch.delenv("SQLBUILD_NO_PROGRESS", raising=False)


def _set_no_progress_env(monkeypatch: pytest.MonkeyPatch, env_value: str | None) -> None:
    monkeypatch.setenv("SQLBUILD_NO_PROGRESS", cast(str, env_value))


def apply_no_progress_env(*, monkeypatch: pytest.MonkeyPatch, env_value: str | None) -> None:
    _NO_PROGRESS_ENV_ACTIONS[env_value is None](monkeypatch, env_value)


_NO_PROGRESS_ENV_ACTIONS: MappingProxyType[
    bool, Callable[[pytest.MonkeyPatch, str | None], None]
] = MappingProxyType({True: _delete_no_progress_env, False: _set_no_progress_env})


class RecordingStream(io.StringIO):
    """In-memory stream that records writes into a shared event log."""

    def __init__(self, *, events: list[str], tty: bool) -> None:
        super().__init__()
        self._events: list[str] = events
        self._tty: bool = tty

    def isatty(self) -> bool:
        return self._tty

    def write(self, text: str) -> int:
        self._events.append(f"write:{text}")
        return super().write(text)


class RecordingSpinnerOwner:
    """Transient line owner that records clear and redraw requests."""

    def __init__(self, *, events: list[str]) -> None:
        self._events: list[str] = events

    def clear_transient_line(self) -> None:
        self._events.append("clear")

    def redraw_transient_line(self) -> None:
        self._events.append("redraw")
