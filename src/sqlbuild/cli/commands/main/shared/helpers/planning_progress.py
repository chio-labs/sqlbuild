"""User-facing plan generation progress messages."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.shared.helpers.colors import dim


class PlanningProgressReporter:
    """Render simple planning phase progress messages."""

    def __init__(self, *, stream: TextIO, use_color: bool = False) -> None:
        self._stream: TextIO = stream
        self._use_color: bool = use_color

    def on_progress(self, message: str) -> None:
        output: str = dim(message) if self._use_color else message
        self._stream.write(f"{output}\n")
        self._stream.flush()
