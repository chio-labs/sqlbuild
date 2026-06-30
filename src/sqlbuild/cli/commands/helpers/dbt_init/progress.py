"""Progress rendering for `sqb dbt init`."""

from __future__ import annotations

import time
from typing import TextIO

from sqlbuild.shared.classes.transient_status_reporter import TransientStatusReporter


class DbtInitProgressReporter:
    """Render timed `sqb dbt init` phase progress."""

    def __init__(self, *, stream: TextIO, use_color: bool) -> None:
        self._stream: TextIO = stream
        self._status: TransientStatusReporter = TransientStatusReporter(
            stream=stream,
            use_color=use_color,
        )
        self._phase_start: float | None = None
        self._started: bool = False

    def start(self, message: str) -> None:
        if not self._started:
            self._stream.write("\n")
            self._stream.flush()
            self._started = True
        self._phase_start = time.perf_counter()
        self._status.start(message)

    def complete(self, message: str) -> None:
        phase_start: float | None = self._phase_start
        elapsed_seconds: float = 0.0 if phase_start is None else time.perf_counter() - phase_start
        self._status.complete(f"{message} ({elapsed_seconds:.2f}s)")
        self._phase_start = None
