"""Verbose per-query warehouse inspection lines written to stderr."""

from __future__ import annotations

import sys
import threading

from sqlbuild.adapter.relations.models import InspectionQueryRecord
from sqlbuild.presentation.main.transient_line_coordinator import shared_transient_line_coordinator

_SQL_PREVIEW_LENGTH: int = 160


class VerboseInspectionWriter:
    """Write each inspection read as one truncated stderr line and keep a running total."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._count: int = 0
        self._seconds: float = 0.0

    def write(self, record: InspectionQueryRecord) -> None:
        """Write one inspection read; safe to call from inspection worker threads."""

        with self._lock:
            self._count += 1
            self._seconds += record.elapsed_seconds
        self._write_line(text=self.format_record(record=record))

    def write_total(self) -> None:
        """Write the read count and cumulative query time when anything was read."""

        if self._count:
            self._write_line(
                text=(
                    f"Inspection queries: {self._count} "
                    f"({self._seconds:.2f}s cumulative query time)"
                )
            )

    @staticmethod
    def format_record(*, record: InspectionQueryRecord) -> str:
        """Render one inspection read as a single truncated diagnostic line."""

        text: str = " ".join(record.sql.split())
        if len(text) > _SQL_PREVIEW_LENGTH:
            text = text[: _SQL_PREVIEW_LENGTH - 3] + "..."
        outcome: str = (
            f"failed: {' '.join(record.error.split())}"
            if record.error is not None
            else _row_count_text(record.row_count)
        )
        return f"  inspect {record.elapsed_seconds:6.2f}s  {outcome}  {text}"

    @staticmethod
    def _write_line(*, text: str) -> None:
        shared_transient_line_coordinator().write_persistent(stream=sys.stderr, text=f"{text}\n")


def _row_count_text(row_count: int | None) -> str:
    if row_count is None:
        return "? rows"
    return f"{row_count} row" if row_count == 1 else f"{row_count} rows"
