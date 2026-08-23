"""Cursor bounds computation from warehouse snapshot and model config."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlbuild.compiler.planner._helpers.output.inclusive_cursor_end import advance_cursor_end
from sqlbuild.compiler.planner.constants import (
    MICROBATCH_END_SENTINEL,
    MICROBATCH_START_SENTINEL,
)
from sqlbuild.compiler.planner.models import CursorBounds, Duration, ModelCursorSnapshot
from sqlbuild.compiler.planner.types import CursorGrain, CursorType


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
    cursor_grain: str | None = None,
) -> CursorBounds | None:
    """Compute effective cursor bounds for one incremental model."""

    if is_microbatch:
        return CursorBounds(start=MICROBATCH_START_SENTINEL, end=MICROBATCH_END_SENTINEL)

    raw_end: str | None = _compute_raw_end(cursor_snapshot)
    if raw_end is None:
        return None
    if cursor_type in {CursorType.INTEGER, CursorType.TIMESTAMP}:
        raw_end = _advance_discovered_end(
            value=raw_end,
            cursor_type=cursor_type,
            cursor_grain=cursor_grain,
        )

    raw_start: str | None = _compute_raw_start(cursor_snapshot)
    if raw_start is None:
        return None

    if start_cursor_override is not None:
        raw_start = start_cursor_override
    if end_cursor_override is not None:
        raw_end = _advance_inclusive_operator_end(
            end_cursor_override=end_cursor_override,
            cursor_type=cursor_type,
            cursor_grain=cursor_grain,
        )

    raw_start = apply_cursor_replay_policy(
        start=raw_start,
        end=raw_end,
        cursor_start=cursor_start,
        cursor_type=cursor_type,
        lookback=lookback,
        backfill_duration=backfill_duration,
        has_start_override=start_cursor_override is not None,
    )

    return CursorBounds(start=raw_start, end=raw_end)


def apply_cursor_replay_policy(
    *,
    start: str,
    end: str,
    cursor_start: str | None,
    cursor_type: str | None,
    lookback: str | None,
    backfill_duration: str | None,
    has_start_override: bool,
) -> str:
    """Apply replay, lookback, and configured lower-bound policy to a cursor start."""

    effective_start: str = start
    if backfill_duration is not None and not has_start_override:
        adjusted_start: str | None = _subtract_duration(value=end, duration=backfill_duration)
        if adjusted_start is not None:
            effective_start = adjusted_start
    if lookback is not None and not has_start_override and backfill_duration is None:
        adjusted_lookback: str | None = _subtract_duration(value=effective_start, duration=lookback)
        if adjusted_lookback is not None:
            effective_start = adjusted_lookback
    return _apply_cursor_start_floor(
        current_start=effective_start,
        cursor_start=cursor_start,
        cursor_type=cursor_type,
    )


def _advance_inclusive_operator_end(
    *,
    end_cursor_override: str,
    cursor_type: str | None,
    cursor_grain: str | None,
) -> str:
    """Advance an inclusive operator end to the exclusive bound so the final value is processed."""

    return advance_cursor_end(
        value=end_cursor_override,
        cursor_type=cursor_type,
        cursor_grain=cursor_grain,
    )


def _advance_discovered_end(
    *, value: str, cursor_type: str | None, cursor_grain: str | None
) -> str:
    if cursor_type == CursorType.TIMESTAMP and cursor_grain in {
        CursorGrain.MONTH,
        CursorGrain.YEAR,
    }:
        plain_date: date | None
        try:
            plain_date = date.fromisoformat(value)
        except ValueError:
            plain_date = None
        duration: Duration = Duration(
            months=1 if cursor_grain == CursorGrain.MONTH else 0,
            years=1 if cursor_grain == CursorGrain.YEAR else 0,
        )
        if plain_date is not None:
            advanced: datetime = duration.add_to(datetime.combine(plain_date, datetime.min.time()))
            return advanced.date().isoformat()
        try:
            return duration.add_to(datetime.fromisoformat(value)).isoformat()
        except ValueError:
            return value
    return advance_cursor_end(
        value=value,
        cursor_type=cursor_type,
        cursor_grain=cursor_grain,
    )


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


def _subtract_duration(*, value: str, duration: str) -> str | None:
    """Subtract a duration string from a cursor value."""

    parsed: Duration | None = Duration.parse(duration)
    if parsed is None:
        return None

    timestamp: datetime | None = _try_parse_timestamp(value)
    if timestamp is not None:
        return parsed.subtract_from(timestamp).isoformat()

    integer: int | None = _try_parse_integer(value)
    if integer is not None:
        return str(integer - parsed.fixed_seconds)

    return None


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
