"""User-facing plan generation progress messages."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.cli.commands.main.shared.helpers.status import TransientStatusReporter


class PlanningProgressReporter:
    """Render simple planning phase progress messages."""

    def __init__(self, *, stream: TextIO, use_color: bool = False) -> None:
        self._status: TransientStatusReporter = TransientStatusReporter(
            stream=stream,
            use_color=use_color,
        )
        self._active: bool = False

    def on_progress(self, message: str) -> None:
        if _is_planning_completion_message(message):
            self._status.complete(message)
            self._active = False
            return
        if not self._active:
            self._status.start(message)
            self._active = True
            return
        self._status.update(message)


def _is_planning_completion_message(message: str) -> bool:
    return message.startswith("Inspected ") or message.startswith("Generated ")
