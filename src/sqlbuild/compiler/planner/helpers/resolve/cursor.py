"""Cursor bounds computation from warehouse snapshot and model config."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlbuild.compiler.planner.helpers.resolve.constants import (
    MICROBATCH_END_SENTINEL,
    MICROBATCH_START_SENTINEL,
)
from sqlbuild.compiler.planner.models import CursorBounds, ModelCursorSnapshot
from sqlbuild.compiler.planner.types import CursorType

_DURATION_PATTERN: re.Pattern[str] = re.compile(r"^(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")


def compute_cursor_bounds(
    *,
    cursor_snapshot: ModelCursorSnapshot,
    cursor_type: str | None,
    cursor_start: str | None,
    lookback: str | None,
    backfill_duration: str | None,
    start_cursor_override: str | None,
    end_cursor_override: str | None,
    is_microbatch: bool,
) -> CursorBounds | None:
    """Compute effective cursor bounds for one incremental model.

    Returns None if no meaningful bounds can be derived (empty upstreams).
    """

    if is_microbatch:
        return CursorBounds(start=MICROBATCH_START_SENTINEL, end=MICROBATCH_END_SENTINEL)

    raw_end: str | None = _compute_raw_end(cursor_snapshot)
    if raw_end is None:
        return None

    raw_start: str | None = _compute_raw_start(cursor_snapshot)
    if raw_start is None:
        return None

    if start_cursor_override is not None:
        raw_start = start_cursor_override
    if end_cursor_override is not None:
        raw_end = end_cursor_override

    if backfill_duration is not None and start_cursor_override is None:
        adjusted_start: str | None = _subtract_duration(raw_end, backfill_duration)
        if adjusted_start is not None:
            raw_start = adjusted_start

    if lookback is not None and start_cursor_override is None and backfill_duration is None:
        adjusted_lookback: str | None = _subtract_duration(raw_start, lookback)
        if adjusted_lookback is not None:
            raw_start = adjusted_lookback

    raw_start = _apply_cursor_start_floor(
        current_start=raw_start,
        cursor_start=cursor_start,
        cursor_type=cursor_type,
    )

    return CursorBounds(start=raw_start, end=raw_end)


def _compute_raw_start(snapshot: ModelCursorSnapshot) -> str | None:
    """Derive the raw start bound from snapshot data."""

    if snapshot.target_max is not None:
        return snapshot.target_max
    if not snapshot.upstream_mins:
        return None
    return min(snapshot.upstream_mins)


def _compute_raw_end(snapshot: ModelCursorSnapshot) -> str | None:
    """Derive the raw end bound from snapshot data."""

    if not snapshot.upstream_maxes:
        return None
    return min(snapshot.upstream_maxes)


def _subtract_duration(value: str, duration: str) -> str | None:
    """Subtract a duration string from a cursor value.

    Handles timestamp strings via datetime parsing and integer strings via
    integer arithmetic with duration-to-seconds conversion.
    """

    td: timedelta | None = _parse_duration(duration)
    if td is None:
        return None

    timestamp: datetime | None = _try_parse_timestamp(value)
    if timestamp is not None:
        adjusted: datetime = timestamp - td
        return adjusted.isoformat()

    integer: int | None = _try_parse_integer(value)
    if integer is not None:
        total_seconds: int = int(td.total_seconds())
        return str(integer - total_seconds)

    return None


def _parse_duration(duration: str) -> timedelta | None:
    """Parse a duration string like '1d', '6h', '30m', '15s' into a timedelta."""

    match: re.Match[str] | None = _DURATION_PATTERN.match(duration)
    if match is None:
        return None
    days: int = int(match.group(1) or 0)
    hours: int = int(match.group(2) or 0)
    minutes: int = int(match.group(3) or 0)
    seconds: int = int(match.group(4) or 0)
    if days == 0 and hours == 0 and minutes == 0 and seconds == 0:
        return None
    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)


def _try_parse_timestamp(value: str) -> datetime | None:
    """Attempt to parse a cursor value as a timestamp."""

    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _try_parse_integer(value: str) -> int | None:
    """Attempt to parse a cursor value as an integer."""

    try:
        decimal_value: Decimal = Decimal(value)
        if decimal_value == int(decimal_value):
            return int(decimal_value)
    except (InvalidOperation, ValueError, OverflowError):
        pass
    return None


def _apply_cursor_start_floor(
    *,
    current_start: str,
    cursor_start: str | None,
    cursor_type: str | None,
) -> str:
    if cursor_start is None:
        return current_start
    if cursor_type == CursorType.TIMESTAMP:
        current_timestamp: datetime | None = _try_parse_timestamp(current_start)
        floor_timestamp: datetime | None = _try_parse_timestamp(cursor_start)
        if current_timestamp is not None and floor_timestamp is not None:
            return max(current_timestamp, floor_timestamp).isoformat()
        return current_start
    if cursor_type == CursorType.INTEGER:
        current_integer: int | None = _try_parse_integer(current_start)
        floor_integer: int | None = _try_parse_integer(cursor_start)
        if current_integer is not None and floor_integer is not None:
            return str(max(current_integer, floor_integer))
    return current_start
