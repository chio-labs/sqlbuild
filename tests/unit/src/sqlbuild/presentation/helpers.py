"""Terminal colour capability fixtures for CLI output tests."""

from __future__ import annotations

import sys
from typing import TextIO

import pytest


class ColorTerminalStream:
    """A text stream that reports a terminal and writes through to the captured stream."""

    def __init__(self, stream: TextIO) -> None:
        self._stream: TextIO = stream

    def isatty(self) -> bool:
        return True

    def write(self, text: str) -> int:
        return self._stream.write(text)

    def flush(self) -> None:
        self._stream.flush()

    def __getattr__(self, name: str) -> object:
        return getattr(self._stream, name)


def use_color_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make `sys.stdout` a colour terminal that still writes to the captured output."""

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys, "stdout", ColorTerminalStream(sys.stdout))


def use_plain_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable terminal colour through `NO_COLOR`."""

    monkeypatch.setenv("NO_COLOR", "1")
