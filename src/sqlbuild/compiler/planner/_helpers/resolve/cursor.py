"""Cursor bounds computation from warehouse snapshot and model config."""

from __future__ import annotations

from datetime import datetime

from sqlbuild.compiler.planner._helpers.output.inclusive_cursor_end import (
    advance_cursor_end,
)
from sqlbuild.compiler.planner._helpers.output.inclusive_cursor_end import (
    advance_discovered_cursor_end as _advance_discovered_cursor_end,
)
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
from sqlbuild.cursor_algebra.constants import GRAIN_ORDER
from sqlbuild.cursor_algebra.main.floor_to_grain import floor_to_grain
from sqlbuild.cursor_algebra.main.max_bound import max_bound
from sqlbuild.cursor_algebra.main.min_bound import min_bound
from sqlbuild.cursor_algebra.main.render import render
from sqlbuild.cursor_algebra.main.try_parse import try_parse
from sqlbuild.cursor_algebra.models import DateValue, IntegerValue, TimestampValue
from sqlbuild.cursor_algebra.types import CursorScalar


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

    raw_start: str | None = _compute_raw_start(snapshot=cursor_snapshot, cursor_type=cursor_type)
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
    """Convert a discovered string maximum to its canonical exclusive partition end."""

    return str(
        _advance_discovered_cursor_end(
            value=value,
            cursor_type=cursor_type,
            cursor_grain=cursor_grain,
        )
    )


def _compute_raw_start(*, snapshot: ModelCursorSnapshot, cursor_type: str | None) -> str | None:
    """Derive the raw start bound from snapshot data."""

    if snapshot.target_max is not None:
        return snapshot.target_max
    starts: tuple[str, ...] = (*snapshot.upstream_mins, *snapshot.upstream_terminal_starts)
    if not starts:
        return None
    return (
        min_bound(values=starts, cursor_type=cursor_type)
        if cursor_type is not None
        else min(starts)
    )


def _compute_raw_end(
    *, snapshot: ModelCursorSnapshot, cursor_type: str | None, cursor_grain: str | None
) -> str | None:
    """Derive the raw end bound from snapshot data."""

    if snapshot.upstream_availability_ends:
        exclusive_ends: tuple[str, ...] = tuple(
            _normalize_timestamp_grain(value=value, grain=cursor_grain)
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
        return (
            max_bound(values=exclusive_ends, cursor_type=cursor_type)
            if cursor_type is not None
            else max(exclusive_ends)
        )
    return (
        min_bound(values=exclusive_ends, cursor_type=cursor_type)
        if cursor_type is not None
        else min(exclusive_ends)
    )


def _subtract_duration(*, value: str, duration: str) -> str | None:
    """Subtract a duration string from a cursor value."""

    parsed: Duration | None = Duration.parse(duration)
    if parsed is None:
        return None

    temporal: CursorScalar | None = try_parse(raw=value, cursor_type=CursorType.TIMESTAMP)
    if isinstance(temporal, TimestampValue):
        return parsed.subtract_from(temporal.value).isoformat()
    if isinstance(temporal, DateValue):
        timestamp: datetime = datetime.combine(temporal.value, datetime.min.time())
        return parsed.subtract_from(timestamp).isoformat()

    integer: CursorScalar | None = try_parse(raw=value, cursor_type=CursorType.INTEGER)
    if isinstance(integer, IntegerValue):
        return str(integer.value - parsed.fixed_seconds)

    return None


def _normalize_timestamp_grain(*, value: str, grain: str) -> str:
    parsed: CursorScalar | None = try_parse(raw=value, cursor_type=CursorType.TIMESTAMP)
    if parsed is None:
        return value
    return render(value=floor_to_grain(value=parsed, grain=CursorGrain(grain)))


def _apply_cursor_start_floor(
    *,
    current_start: str,
    cursor_start: str | None,
    cursor_type: str | None,
) -> str:
    if cursor_start is None:
        return current_start
    if cursor_type == CursorType.TIMESTAMP:
        current_scalar: CursorScalar | None = try_parse(
            raw=current_start, cursor_type=CursorType.TIMESTAMP
        )
        floor_scalar: CursorScalar | None = try_parse(
            raw=cursor_start, cursor_type=CursorType.TIMESTAMP
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
            return render(
                value=max_bound(
                    values=(current_timestamp, floor_timestamp), cursor_type=CursorType.TIMESTAMP
                )
            )
        return current_start
    if cursor_type == CursorType.INTEGER:
        current_integer: CursorScalar | None = try_parse(
            raw=current_start, cursor_type=CursorType.INTEGER
        )
        floor_integer: CursorScalar | None = try_parse(
            raw=cursor_start, cursor_type=CursorType.INTEGER
        )
        if current_integer is not None and floor_integer is not None:
            return render(
                value=max_bound(
                    values=(current_integer, floor_integer), cursor_type=CursorType.INTEGER
                )
            )
    return current_start
