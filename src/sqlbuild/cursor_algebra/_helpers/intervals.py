"""Private half-open cursor interval algebra."""

from datetime import datetime, timedelta

from sqlbuild.compiler.planner.types import CursorGrain
from sqlbuild.cursor_algebra._helpers.arithmetic import (
    advance_scalar,
    advance_scalar_by,
    floor_scalar,
)
from sqlbuild.cursor_algebra._helpers.comparison import compare_scalars, comparison_value
from sqlbuild.cursor_algebra.constants import GRAIN_FIXED_STEP
from sqlbuild.cursor_algebra.exceptions import CursorAlgebraError
from sqlbuild.cursor_algebra.models import (
    AlignedInterval,
    DateValue,
    IntegerValue,
    TimestampValue,
)
from sqlbuild.cursor_algebra.types import CursorScalar


def observed_partition_value(*, value: CursorScalar, grain: CursorGrain | None) -> AlignedInterval:
    """Return the canonical partition containing a physical value."""

    if isinstance(value, IntegerValue):
        return AlignedInterval(start=value, end=IntegerValue(value=value.value + 1), grain=None)
    if grain is None:
        raise CursorAlgebraError("temporal observed partitions require a grain")
    if isinstance(value, DateValue) and grain in {
        CursorGrain.SECOND,
        CursorGrain.MINUTE,
        CursorGrain.HOUR,
    }:
        value = TimestampValue(value=datetime.combine(value.value, datetime.min.time()))
    start: CursorScalar = floor_scalar(value=value, grain=grain)
    return AlignedInterval(start=start, end=advance_scalar(value=start, grain=grain), grain=grain)


def shift_inclusive_bound(
    *, value: CursorScalar, grain: CursorGrain | None, direction: int
) -> CursorScalar:
    """Shift an inclusive/exclusive boundary by one compatibility unit."""

    if isinstance(value, IntegerValue):
        return IntegerValue(value=value.value + direction)
    if grain is None:
        raise CursorAlgebraError("temporal inclusive bounds require a grain")
    if isinstance(value, DateValue):
        return DateValue(value=value.value + timedelta(days=direction))
    step: timedelta = GRAIN_FIXED_STEP[grain] or timedelta(days=1)
    return TimestampValue(value=value.value + direction * step)


def clamp_interval(*, interval: AlignedInterval, bounds: AlignedInterval) -> AlignedInterval | None:
    """Intersect two canonical intervals."""

    start: CursorScalar = (
        interval.start
        if compare_scalars(left=interval.start, right=bounds.start) >= 0
        else bounds.start
    )
    end: CursorScalar = (
        interval.end if compare_scalars(left=interval.end, right=bounds.end) <= 0 else bounds.end
    )
    if compare_scalars(left=start, right=end) >= 0:
        return None
    return AlignedInterval(start=start, end=end, grain=interval.grain)


def merge_interval_values(*, intervals: tuple[AlignedInterval, ...]) -> tuple[AlignedInterval, ...]:
    """Merge overlapping or adjacent canonical intervals."""

    ordered: list[AlignedInterval] = sorted(
        intervals, key=lambda interval: comparison_value(value=interval.start)
    )
    merged: list[AlignedInterval] = []
    for interval in ordered:
        if not merged or compare_scalars(left=merged[-1].end, right=interval.start) < 0:
            merged.append(interval)
        elif compare_scalars(left=merged[-1].end, right=interval.end) < 0:
            merged[-1] = AlignedInterval(
                start=merged[-1].start, end=interval.end, grain=interval.grain
            )
    return tuple(merged)


def split_interval(*, interval: AlignedInterval, step: int) -> tuple[AlignedInterval, ...]:
    """Split a canonical interval by a positive number of grain units."""

    if step <= 0:
        raise CursorAlgebraError("cursor batch step must be positive")
    batches: list[AlignedInterval] = []
    start: CursorScalar = interval.start
    while compare_scalars(left=start, right=interval.end) < 0:
        end: CursorScalar = advance_scalar_by(value=start, grain=interval.grain, steps=step)
        if compare_scalars(left=end, right=interval.end) > 0:
            end = interval.end
        batches.append(AlignedInterval(start=start, end=end, grain=interval.grain))
        start = end
    return tuple(batches)
