"""Inclusive cursor end-bound formatting helpers."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlbuild.compiler.planner.constants import WHOLE_DAY_CURSOR_GRAINS
from sqlbuild.compiler.planner.types import CursorGrain, CursorType


def inclusive_cursor_end(
    *,
    end: str,
    cursor_type: str | None,
    cursor_grain: str | None,
) -> str:
    """Return the last cursor value included by an exclusive end bound."""

    if cursor_type == CursorType.INTEGER:
        return _inclusive_integer_end(end=end)
    return _inclusive_timestamp_end(end=end, cursor_grain=cursor_grain)


def _inclusive_integer_end(*, end: str) -> str:
    try:
        return str(int(Decimal(end)) - 1)
    except (InvalidOperation, ValueError):
        return end


def _inclusive_timestamp_end(*, end: str, cursor_grain: str | None) -> str:
    try:
        parsed: datetime = datetime.fromisoformat(end)
    except ValueError:
        return end
    if _has_no_time_component(value=parsed):
        inclusive_date: date = (parsed - timedelta(days=1)).date()
        return inclusive_date.isoformat()
    return (parsed - _grain_step(cursor_grain=cursor_grain)).isoformat()


def _grain_step(*, cursor_grain: str | None) -> timedelta:
    if cursor_grain == CursorGrain.MINUTE:
        return timedelta(minutes=1)
    if cursor_grain == CursorGrain.HOUR:
        return timedelta(hours=1)
    if cursor_grain in WHOLE_DAY_CURSOR_GRAINS:
        return timedelta(days=1)
    return timedelta(seconds=1)


def _has_no_time_component(*, value: datetime) -> bool:
    return (value.hour, value.minute, value.second, value.microsecond) == (0, 0, 0, 0)
