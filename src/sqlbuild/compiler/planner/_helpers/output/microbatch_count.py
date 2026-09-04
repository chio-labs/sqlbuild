"""Planner-private microbatch count calculation."""

from __future__ import annotations

from datetime import datetime

from sqlbuild.compiler.planner.models import CursorBounds, Duration
from sqlbuild.compiler.planner.types import CursorType
from sqlbuild.cursor_algebra.models import DateValue, IntegerValue, TimestampValue


def count_microbatches(
    *, bounds: CursorBounds, batch_size: str, cursor_type: str, equal_bounds_are_batch: bool = False
) -> int:
    """Count batches for one concrete cursor range."""

    if cursor_type == CursorType.INTEGER:
        if not isinstance(bounds.start, IntegerValue) or not isinstance(bounds.end, IntegerValue):
            return 0
        start: int = bounds.start.value
        end: int = bounds.end.value
        try:
            size: int = int(batch_size)
        except ValueError:
            return 0
        if equal_bounds_are_batch and start == end:
            return 1
        if size <= 0 or start >= end:
            return 0
        return (end - start + size - 1) // size
    if cursor_type != CursorType.TIMESTAMP:
        return 0
    duration: Duration | None = Duration.parse(batch_size)
    if duration is None:
        return 0
    if not isinstance(bounds.start, DateValue | TimestampValue) or not isinstance(
        bounds.end, DateValue | TimestampValue
    ):
        return 0
    current: datetime = (
        bounds.start.value
        if isinstance(bounds.start, TimestampValue)
        else datetime.combine(bounds.start.value, datetime.min.time())
    )
    end_at: datetime = (
        bounds.end.value
        if isinstance(bounds.end, TimestampValue)
        else datetime.combine(bounds.end.value, datetime.min.time())
    )
    if equal_bounds_are_batch and current == end_at:
        return 1
    count: int = 0
    while current < end_at:
        current = min(duration.add_to(current), end_at)
        count += 1
    return count
