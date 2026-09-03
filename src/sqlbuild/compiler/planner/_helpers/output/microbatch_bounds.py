"""Planner-private microbatch range capping."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlbuild.compiler.planner.models import CursorBounds, Duration
from sqlbuild.compiler.planner.types import CursorType
from sqlbuild.spec.contracts.types import MicrobatchLimitAction


def cap_microbatch_bounds(
    *,
    bounds: CursorBounds,
    batch_size: str,
    cursor_type: str,
    max_batches: int,
    action: MicrobatchLimitAction,
) -> CursorBounds:
    """Cap one concrete range to its earliest or latest batch windows."""

    if action not in {
        MicrobatchLimitAction.CAP_FROM_END,
        MicrobatchLimitAction.CAP_FROM_START,
    }:
        return bounds
    if cursor_type == CursorType.INTEGER:
        try:
            start: int = int(Decimal(bounds.start))
            end: int = int(Decimal(bounds.end))
            size: int = int(Decimal(batch_size))
        except (InvalidOperation, ValueError, OverflowError):
            return bounds
        if size <= 0:
            return bounds
        if action == MicrobatchLimitAction.CAP_FROM_START:
            return CursorBounds(start=bounds.start, end=str(min(end, start + size * max_batches)))
        batch_count: int = max(0, (end - start + size - 1) // size)
        skipped_batches: int = max(0, batch_count - max_batches)
        return CursorBounds(start=str(start + size * skipped_batches), end=bounds.end)

    if cursor_type != CursorType.TIMESTAMP:
        return bounds
    duration: Duration | None = Duration.parse(batch_size)
    if duration is None:
        return bounds
    try:
        start_at: datetime = datetime.fromisoformat(bounds.start)
        end_at: datetime = datetime.fromisoformat(bounds.end)
    except (TypeError, ValueError):
        return bounds
    if action == MicrobatchLimitAction.CAP_FROM_START:
        capped_end: datetime = start_at
        for _ in range(max_batches):
            capped_end = min(duration.add_to(capped_end), end_at)
        return CursorBounds(start=bounds.start, end=capped_end.isoformat())
    boundaries: list[datetime] = [start_at]
    while boundaries[-1] < end_at:
        boundaries.append(min(duration.add_to(boundaries[-1]), end_at))
    capped_start: datetime = boundaries[max(0, len(boundaries) - 1 - max_batches)]
    return CursorBounds(start=capped_start.isoformat(), end=bounds.end)
