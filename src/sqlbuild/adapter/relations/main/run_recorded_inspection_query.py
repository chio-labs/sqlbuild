"""Run and record one planner warehouse inspection read."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.relations._helpers.inspection_context import emit_inspection_record
from sqlbuild.adapter.relations.models import InspectionQueryRecord


def run_recorded_inspection_query(*, sql: str, run: Callable[[], list[Any]]) -> list[Any]:
    """Run one inspection read, then record its text, elapsed time, and row count."""

    started: float = time.monotonic()
    try:
        rows: list[Any] = run()
    except Exception as error:
        _ = emit_inspection_record(
            record=InspectionQueryRecord(
                sql=sql,
                elapsed_seconds=time.monotonic() - started,
                row_count=None,
                error=str(error),
            )
        )
        raise
    _ = emit_inspection_record(
        record=InspectionQueryRecord(
            sql=sql, elapsed_seconds=time.monotonic() - started, row_count=len(rows)
        )
    )
    return rows
