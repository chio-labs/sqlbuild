"""Cursor bounds computation from warehouse snapshot and model config."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from sqlbuild.compiler.planner._helpers.output.inclusive_cursor_end import advance_cursor_end
from sqlbuild.compiler.planner.constants import (
    MICROBATCH_END_SENTINEL,
    MICROBATCH_START_SENTINEL,
)
from sqlbuild.compiler.planner.models import (
    CursorBounds,
    Duration,
    MaximumStartPolicyInputs,
    ModelCursorSnapshot,
)
from sqlbuild.compiler.planner.types import (
    CursorGrain,
    CursorType,
    CursorWatermarkMode,
    MicrobatchStrategy,
)

_TIMESTAMP_GRAIN_ORDER: dict[str, int] = {
    CursorGrain.SECOND: 0,
    CursorGrain.MINUTE: 1,
    CursorGrain.HOUR: 2,
    CursorGrain.DAY: 3,
    CursorGrain.MONTH: 4,
    CursorGrain.YEAR: 5,
}


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
    maximum_start_policy: MaximumStartPolicyInputs | None = None,
) -> CursorBounds | None:
    """Compute effective cursor bounds for one incremental model."""

    if is_microbatch:
        return CursorBounds(start=MICROBATCH_START_SENTINEL, end=MICROBATCH_END_SENTINEL)
    if not cursor_snapshot.watermarks_available:
        return None

    raw_end: str | None = _compute_raw_end(
        snapshot=cursor_snapshot, cursor_type=cursor_type, cursor_grain=cursor_grain
    )
    if raw_end is None:
        return None

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

    bounds: CursorBounds = CursorBounds(start=raw_start, end=raw_end)
    from sqlbuild.compiler.planner._helpers.resolve.maximum_start import (
        apply_maximum_start_policy,
    )

    bounds = apply_maximum_start_policy(
        bounds=bounds,
        snapshot=cursor_snapshot,
        cursor_type=cursor_type,
        cursor_grain=cursor_grain,
        cursor_start=cursor_start,
        lookback=lookback,
        backfill_duration=backfill_duration,
        policy=maximum_start_policy or MaximumStartPolicyInputs(),
        has_start_override=start_cursor_override is not None,
    )
    return bounds.clamp_to_availability(
        ranges=cursor_snapshot.upstream_availability_ranges,
        cursor_watermark_mode=cursor_snapshot.cursor_watermark_mode,
        cursor_type=cursor_type,
    )


def resolve_effective_timestamp_grain(
    *,
    cursor_type: str | None,
    downstream_grain: str | None,
    cursor_input_grains: tuple[str | None, ...],
    microbatch_strategy: str | None = None,
) -> str | None:
    """Return the coarsest timestamp grain participating in cursor replay."""

    if cursor_type != CursorType.TIMESTAMP:
        return None
    if microbatch_strategy == MicrobatchStrategy.WATERMARK:
        return downstream_grain or CursorGrain.SECOND
    effective: str = downstream_grain or CursorGrain.SECOND
    input_grain: str | None
    for input_grain in cursor_input_grains:
        candidate: str = input_grain or CursorGrain.SECOND
        if _TIMESTAMP_GRAIN_ORDER[candidate] > _TIMESTAMP_GRAIN_ORDER[effective]:
            effective = candidate
    return effective


def normalize_cursor_snapshot_grain(
    *,
    cursor_snapshot: ModelCursorSnapshot,
    cursor_type: str | None,
    effective_grain: str | None,
) -> ModelCursorSnapshot:
    """Floor timestamp snapshot values to the effective replay grain."""

    if cursor_type != CursorType.TIMESTAMP or effective_grain is None:
        return cursor_snapshot
    return ModelCursorSnapshot(
        target_max=(
            _floor_timestamp_string(value=cursor_snapshot.target_max, grain=effective_grain)
            if cursor_snapshot.target_max is not None
            else None
        ),
        upstream_mins=tuple(
            _floor_timestamp_string(value=value, grain=effective_grain)
            for value in cursor_snapshot.upstream_mins
        ),
        upstream_maxes=tuple(
            _floor_timestamp_string(value=value, grain=effective_grain)
            for value in cursor_snapshot.upstream_maxes
        ),
        physical_target_max=cursor_snapshot.physical_target_max or cursor_snapshot.target_max,
        target_eligible_max=(
            _floor_timestamp_string(
                value=cursor_snapshot.target_eligible_max, grain=effective_grain
            )
            if cursor_snapshot.target_eligible_max is not None
            else None
        ),
        target_relation=cursor_snapshot.target_relation,
        destination_cursor_column=cursor_snapshot.destination_cursor_column,
        input_evidence=cursor_snapshot.input_evidence,
        expected_watermark_count=cursor_snapshot.expected_watermark_count,
        unavailable_watermark_tags=cursor_snapshot.unavailable_watermark_tags,
        cursor_watermark_mode=cursor_snapshot.cursor_watermark_mode,
        upstream_terminal_starts=cursor_snapshot.upstream_terminal_starts,
        upstream_terminal_ends=cursor_snapshot.upstream_terminal_ends,
        upstream_end_inputs=tuple(
            (
                _floor_timestamp_string(value=physical, grain=effective_grain)
                if physical is not None
                else None,
                terminal,
            )
            for physical, terminal in cursor_snapshot.upstream_end_inputs
        ),
        upstream_availability_ends=cursor_snapshot.upstream_availability_ends,
        upstream_availability_ranges=tuple(
            (
                (
                    _floor_timestamp_string(value=start, grain=effective_grain)
                    if start is not None
                    else None
                ),
                _floor_timestamp_string(value=end, grain=effective_grain),
            )
            for start, end in cursor_snapshot.upstream_availability_ranges
        ),
    )


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


def advance_discovered_cursor_end(
    *, value: str, cursor_type: str | None, cursor_grain: str | None
) -> str:
    if cursor_type is None:
        return value
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
    starts: tuple[str, ...] = (*snapshot.upstream_mins, *snapshot.upstream_terminal_starts)
    if not starts:
        return None
    return min(starts)


def _compute_raw_end(
    *, snapshot: ModelCursorSnapshot, cursor_type: str | None, cursor_grain: str | None
) -> str | None:
    """Derive the raw end bound from snapshot data."""

    if snapshot.upstream_availability_ends:
        exclusive_ends: tuple[str, ...] = tuple(
            _floor_timestamp_string(value=value, grain=cursor_grain)
            if cursor_type == CursorType.TIMESTAMP and cursor_grain is not None
            else value
            for value in snapshot.upstream_availability_ends
        )
    elif snapshot.upstream_end_inputs:
        exclusive_ends: tuple[str, ...] = tuple(
            terminal
            if terminal is not None
            else advance_discovered_cursor_end(
                value=physical or "", cursor_type=cursor_type, cursor_grain=cursor_grain
            )
            for physical, terminal in snapshot.upstream_end_inputs
            if terminal is not None or physical is not None
        )
    else:
        exclusive_ends = (
            tuple(
                advance_discovered_cursor_end(
                    value=value, cursor_type=cursor_type, cursor_grain=cursor_grain
                )
                for value in snapshot.upstream_maxes
            )
            + snapshot.upstream_terminal_ends
        )
    if not exclusive_ends:
        return None
    if snapshot.cursor_watermark_mode == CursorWatermarkMode.ANY:
        return max(exclusive_ends)
    return min(exclusive_ends)


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


def _floor_timestamp_string(*, value: str, grain: str) -> str:
    plain_date: date | None
    try:
        plain_date = date.fromisoformat(value)
    except ValueError:
        plain_date = None
    if plain_date is not None:
        if grain == CursorGrain.MONTH:
            plain_date = plain_date.replace(day=1)
        elif grain == CursorGrain.YEAR:
            plain_date = plain_date.replace(month=1, day=1)
        return plain_date.isoformat()
    parsed: datetime | None = _try_parse_timestamp(value)
    if parsed is None:
        return value
    if grain == CursorGrain.SECOND:
        floored: datetime = parsed.replace(microsecond=0)
    elif grain == CursorGrain.MINUTE:
        floored = parsed.replace(second=0, microsecond=0)
    elif grain == CursorGrain.HOUR:
        floored = parsed.replace(minute=0, second=0, microsecond=0)
    elif grain == CursorGrain.DAY:
        floored = parsed.replace(hour=0, minute=0, second=0, microsecond=0)
    elif grain == CursorGrain.MONTH:
        floored = parsed.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif grain == CursorGrain.YEAR:
        floored = parsed.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        floored = parsed
    return floored.isoformat()


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
