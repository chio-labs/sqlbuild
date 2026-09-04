"""Merge canonical microbatch intervals."""

from datetime import datetime
from decimal import Decimal

from sqlbuild.compiler.planner.types import CursorType
from sqlbuild.microbatches.exceptions import MicrobatchStateError
from sqlbuild.microbatches.models import MicrobatchInterval


def merge_intervals(
    *, intervals: tuple[MicrobatchInterval, ...], cursor_type: str
) -> tuple[MicrobatchInterval, ...]:
    """Merge overlapping or adjacent intervals while preserving disjoint sets."""

    ordered: tuple[MicrobatchInterval, ...] = tuple(
        sorted(
            intervals,
            key=lambda interval: _cursor_value(value=interval.start, cursor_type=cursor_type),
        )
    )
    merged: list[MicrobatchInterval] = []
    for interval in ordered:
        if not merged or _lt(left=merged[-1].end, right=interval.start, cursor_type=cursor_type):
            merged.append(interval)
            continue
        if _lt(left=merged[-1].end, right=interval.end, cursor_type=cursor_type):
            merged[-1] = MicrobatchInterval(start=merged[-1].start, end=interval.end)
    return tuple(merged)


def _cursor_value(*, value: str, cursor_type: str) -> datetime | Decimal:
    if cursor_type == CursorType.TIMESTAMP:
        return datetime.fromisoformat(value)
    if cursor_type == CursorType.INTEGER:
        return Decimal(value)
    raise MicrobatchStateError(f"unsupported cursor type: {cursor_type}")


def _lt(*, left: str, right: str, cursor_type: str) -> bool:
    if cursor_type == CursorType.TIMESTAMP:
        return datetime.fromisoformat(left) < datetime.fromisoformat(right)
    if cursor_type == CursorType.INTEGER:
        return Decimal(left) < Decimal(right)
    raise MicrobatchStateError(f"unsupported cursor type: {cursor_type}")
