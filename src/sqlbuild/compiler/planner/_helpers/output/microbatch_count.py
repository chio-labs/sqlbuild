"""Planner-private microbatch count calculation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlbuild.compiler.planner.models import CursorBounds, Duration
from sqlbuild.compiler.planner.types import CursorType


def count_microbatches(
    *, bounds: CursorBounds, batch_size: str, cursor_type: str, equal_bounds_are_batch: bool = False
) -> int:
    """Count batches for one concrete cursor range."""

    if cursor_type == CursorType.INTEGER:
        try:
            start: int = int(Decimal(bounds.start))
            end: int = int(Decimal(bounds.end))
            size: int = int(Decimal(batch_size))
        except (InvalidOperation, ValueError, OverflowError):
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
    try:
        current: datetime = datetime.fromisoformat(bounds.start)
        end_at: datetime = datetime.fromisoformat(bounds.end)
    except (TypeError, ValueError):
        return 0
    if equal_bounds_are_batch and current == end_at:
        return 1
    count: int = 0
    while current < end_at:
        current = min(duration.add_to(current), end_at)
        count += 1
    return count
