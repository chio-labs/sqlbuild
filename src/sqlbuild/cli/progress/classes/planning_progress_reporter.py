"""User-facing plan generation progress reporter."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.cli.progress.classes.native_progress_projector import (
    NativeProgressProjector,
    current_native_progress_projector,
)
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter

_PROJECT_COMPILE_OPERATION: str = "project_compile"


class PlanningProgressReporter:
    """Render simple planning phase progress messages."""

    def __init__(self, *, stream: TextIO, use_color: bool = False) -> None:
        self._status: TransientStatusReporter = TransientStatusReporter(
            stream=stream,
            use_color=use_color,
        )
        self._active: bool = False
        self._projector: NativeProgressProjector | None = current_native_progress_projector()

    def on_progress(self, message: str) -> None:
        if self._projector is not None and self._projector.is_operation_active(
            operation_name=_PROJECT_COMPILE_OPERATION
        ):
            return
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
        self._status.complete(message=message)
        self._active = False

    def complete_styled(self, message: str) -> None:
        """Complete with a pre-styled message written verbatim."""

        self._status.complete_styled(message=message)
        self._active = False

    def error(self, message: str) -> None:
        """Close active progress and render a non-success terminal message."""

        self._status.error(message)
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
