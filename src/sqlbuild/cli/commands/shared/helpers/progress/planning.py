"""User-facing plan generation progress messages."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.shared.classes.transient_status_reporter import TransientStatusReporter


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
            self.complete(message)
            return
        if not self._active:
            self.start(message)
            return
        self.update(message)

    def start(self, message: str) -> None:
        self._status.start(message)
        self._active = True

    def update(self, message: str) -> None:
        if not self._active:
            self.start(message)
            return
        self._status.update(message)

    def complete(self, message: str) -> None:
        self._status.complete(message)
        self._active = False

    def finish(self, *, blank_line_after: bool = False) -> None:
        self._status.close()
        self._active = False
        if blank_line_after:
            self._status.write_blank_line()


def _is_planning_completion_message(message: str) -> bool:
    return message.startswith(
        (
            "Built ",
            "Checked ",
            "Compiled ",
            "Applied ",
            "Finalized ",
            "Generated ",
            "Inspected ",
            "Loaded ",
            "Planned ",
            "Recorded ",
            "Refreshed ",
            "Resolved ",
            "Cloned ",
        )
    )
