"""Cursor bounds computation from warehouse snapshot and model config."""

from __future__ import annotations

from datetime import datetime

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
from sqlbuild.cursor_algebra.constants import GRAIN_ORDER
from sqlbuild.cursor_algebra.exceptions import CursorAlgebraError
from sqlbuild.cursor_algebra.main.floor_to_grain import floor_to_grain
from sqlbuild.cursor_algebra.main.inclusive_to_exclusive import inclusive_to_exclusive
from sqlbuild.cursor_algebra.main.max_bound import max_bound
from sqlbuild.cursor_algebra.main.min_bound import min_bound
from sqlbuild.cursor_algebra.main.observed_partition import observed_partition
from sqlbuild.cursor_algebra.main.try_parse import try_parse
from sqlbuild.cursor_algebra.models import DateValue, IntegerValue, TimestampValue
from sqlbuild.cursor_algebra.types import BoundSentinel, CursorScalar


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
        return CursorBounds(start=BoundSentinel.START, end=BoundSentinel.END)
    if not cursor_snapshot.watermarks_available:
        return None

    raw_end: CursorScalar | None = _compute_raw_end(
        snapshot=cursor_snapshot, cursor_type=cursor_type, cursor_grain=cursor_grain
    )
    if raw_end is None:
        return None

    raw_start: CursorScalar | None = _compute_raw_start(
        snapshot=cursor_snapshot, cursor_type=cursor_type
    )
    if raw_start is None:
        return None

    if start_cursor_override is not None:
        raw_start = _parse_required(value=start_cursor_override, cursor_type=cursor_type)
    if end_cursor_override is not None:
        raw_end = inclusive_to_exclusive(
            value=_parse_required(value=end_cursor_override, cursor_type=cursor_type),
            grain=(
                None
                if cursor_type == CursorType.INTEGER
                else CursorGrain(cursor_grain or CursorGrain.SECOND)
            ),
        )

    raw_start = apply_typed_cursor_replay_policy(
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

    return apply_maximum_start_policy(
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
        if GRAIN_ORDER[CursorGrain(candidate)] > GRAIN_ORDER[CursorGrain(effective)]:
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
            _normalize_timestamp_grain(value=cursor_snapshot.target_max, grain=effective_grain)
            if cursor_snapshot.target_max is not None
            else None
        ),
        upstream_mins=tuple(
            _normalize_timestamp_grain(value=value, grain=effective_grain)
            for value in cursor_snapshot.upstream_mins
        ),
        upstream_maxes=tuple(
            _normalize_timestamp_grain(value=value, grain=effective_grain)
            for value in cursor_snapshot.upstream_maxes
        ),
        physical_target_max=cursor_snapshot.physical_target_max or cursor_snapshot.target_max,
        target_eligible_max=(
            _normalize_timestamp_grain(
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
                _normalize_timestamp_grain(value=physical, grain=effective_grain)
                if physical is not None
                else None,
                terminal,
            )
            for physical, terminal in cursor_snapshot.upstream_end_inputs
        ),
        upstream_availability_ends=cursor_snapshot.upstream_availability_ends,
    )


def apply_typed_cursor_replay_policy(
    *,
    start: CursorScalar,
    end: CursorScalar,
    cursor_start: CursorScalar | str | None,
    cursor_type: str | None,
    lookback: Duration | str | None,
    backfill_duration: Duration | str | None,
    has_start_override: bool,
) -> CursorScalar:
    """Apply replay, lookback, and configured lower-bound policy to a typed cursor start."""

    effective_start: CursorScalar = start
    if backfill_duration is not None and not has_start_override:
        adjusted_start: CursorScalar | None = _subtract_duration(
            value=end, duration=backfill_duration
        )
        if adjusted_start is not None:
            effective_start = adjusted_start
    if lookback is not None and not has_start_override and backfill_duration is None:
        adjusted_lookback: CursorScalar | None = _subtract_duration(
            value=effective_start, duration=lookback
        )
        if adjusted_lookback is not None:
            effective_start = adjusted_lookback
    return _apply_cursor_start_floor(
        current_start=effective_start,
        cursor_start=cursor_start,
        cursor_type=cursor_type,
    )


def _compute_raw_start(
    *, snapshot: ModelCursorSnapshot, cursor_type: str | None
) -> CursorScalar | None:
    """Derive the raw start bound from snapshot data."""

    if snapshot.target_max is not None:
        return snapshot.target_max
    starts: tuple[CursorScalar, ...] = (
        *snapshot.upstream_mins,
        *snapshot.upstream_terminal_starts,
    )
    if not starts:
        return None
    return min_bound(values=starts, cursor_type=cursor_type or CursorType.TIMESTAMP)


def _compute_raw_end(
    *, snapshot: ModelCursorSnapshot, cursor_type: str | None, cursor_grain: str | None
) -> CursorScalar | None:
    """Derive the raw end bound from snapshot data."""

    if snapshot.upstream_availability_ends:
        exclusive_ends: tuple[CursorScalar, ...] = tuple(
            _normalize_timestamp_grain(value=value, grain=cursor_grain)
            if cursor_type == CursorType.TIMESTAMP and cursor_grain is not None
            else value
            for value in snapshot.upstream_availability_ends
        )
    elif snapshot.upstream_end_inputs:
        exclusive_ends = tuple(
            terminal
            if terminal is not None
            else _advance_typed_discovered_cursor_end(
                value=physical,
                cursor_type=cursor_type,
                cursor_grain=cursor_grain,
            )
            for physical, terminal in snapshot.upstream_end_inputs
            if terminal is not None or physical is not None
        )
    else:
        exclusive_ends = (
            tuple(
                _advance_typed_discovered_cursor_end(
                    value=value, cursor_type=cursor_type, cursor_grain=cursor_grain
                )
                for value in snapshot.upstream_maxes
            )
            + snapshot.upstream_terminal_ends
        )
    if not exclusive_ends:
        return None
    if snapshot.cursor_watermark_mode == CursorWatermarkMode.ANY:
        return max_bound(values=exclusive_ends, cursor_type=cursor_type or CursorType.TIMESTAMP)
    return min_bound(values=exclusive_ends, cursor_type=cursor_type or CursorType.TIMESTAMP)


def _subtract_duration(*, value: CursorScalar, duration: Duration | str) -> CursorScalar | None:
    """Subtract a duration string from a cursor value."""

    parsed: Duration | None = (
        duration if isinstance(duration, Duration) else Duration.parse(duration)
    )
    if parsed is None:
        return None

    if isinstance(value, TimestampValue):
        return TimestampValue(value=parsed.subtract_from(value.value))
    if isinstance(value, DateValue):
        timestamp: datetime = datetime.combine(value.value, datetime.min.time())
        return TimestampValue(value=parsed.subtract_from(timestamp))
    if isinstance(value, IntegerValue):
        return IntegerValue(value=value.value - parsed.fixed_seconds)

    return None


def _normalize_timestamp_grain(*, value: CursorScalar, grain: str) -> CursorScalar:
    return floor_to_grain(value=value, grain=CursorGrain(grain))


def _apply_cursor_start_floor(
    *,
    current_start: CursorScalar,
    cursor_start: CursorScalar | str | None,
    cursor_type: str | None,
) -> CursorScalar:
    if cursor_start is None:
        return current_start
    if cursor_type == CursorType.TIMESTAMP:
        current_scalar: CursorScalar = current_start
        floor_scalar: CursorScalar | None = (
            cursor_start
            if isinstance(cursor_start, TimestampValue | DateValue | IntegerValue)
            else try_parse(raw=cursor_start, cursor_type=CursorType.TIMESTAMP)
        )
        current_timestamp: TimestampValue | None = (
            current_scalar
            if isinstance(current_scalar, TimestampValue)
            else TimestampValue(value=datetime.combine(current_scalar.value, datetime.min.time()))
            if isinstance(current_scalar, DateValue)
            else None
        )
        floor_timestamp: TimestampValue | None = (
            floor_scalar
            if isinstance(floor_scalar, TimestampValue)
            else TimestampValue(value=datetime.combine(floor_scalar.value, datetime.min.time()))
            if isinstance(floor_scalar, DateValue)
            else None
        )
        if current_timestamp is not None and floor_timestamp is not None:
            return max_bound(
                values=(current_timestamp, floor_timestamp), cursor_type=CursorType.TIMESTAMP
            )
        return current_start
    if cursor_type == CursorType.INTEGER:
        current_integer: CursorScalar = current_start
        floor_integer: CursorScalar | None = (
            cursor_start
            if isinstance(cursor_start, TimestampValue | DateValue | IntegerValue)
            else try_parse(raw=cursor_start, cursor_type=CursorType.INTEGER)
        )
        if current_integer is not None and floor_integer is not None:
            return max_bound(
                values=(current_integer, floor_integer), cursor_type=CursorType.INTEGER
            )
    return current_start


def _advance_typed_discovered_cursor_end(
    *, value: CursorScalar | None, cursor_type: str | None, cursor_grain: str | None
) -> CursorScalar:
    if value is None:
        raise CursorAlgebraError("a discovered cursor value is required")
    if cursor_type not in {CursorType.INTEGER, CursorType.TIMESTAMP}:
        return value
    grain: CursorGrain | None = (
        None
        if cursor_type == CursorType.INTEGER
        else CursorGrain(
            cursor_grain
            or (CursorGrain.SECOND if isinstance(value, TimestampValue) else CursorGrain.DAY)
        )
    )
    return observed_partition(value=value, grain=grain).end


def _parse_required(*, value: str, cursor_type: str | None) -> CursorScalar:
    parsed: CursorScalar | None = try_parse(
        raw=value, cursor_type=cursor_type or CursorType.TIMESTAMP
    )
    if parsed is None:
        raise CursorAlgebraError(f"invalid cursor value: {value}")
    return parsed
