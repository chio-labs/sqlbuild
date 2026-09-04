"""Merge canonical microbatch intervals."""

from sqlbuild.compiler.planner.types import CursorType
from sqlbuild.cursor_algebra.main.compare import compare
from sqlbuild.cursor_algebra.main.cursor_sort_key import cursor_sort_key
from sqlbuild.cursor_algebra.main.merge import merge
from sqlbuild.cursor_algebra.main.parse import parse
from sqlbuild.cursor_algebra.main.render import render
from sqlbuild.cursor_algebra.models import AlignedInterval, IntegerValue
from sqlbuild.cursor_algebra.types import CursorScalar
from sqlbuild.microbatches.exceptions import MicrobatchStateError
from sqlbuild.microbatches.models import MicrobatchInterval


def merge_intervals(
    *, intervals: tuple[MicrobatchInterval, ...], cursor_type: str
) -> tuple[MicrobatchInterval, ...]:
    """Merge overlapping or adjacent intervals while preserving disjoint sets."""

    if cursor_type not in {CursorType.TIMESTAMP, CursorType.INTEGER}:
        raise MicrobatchStateError(f"unsupported cursor type: {cursor_type}")
    if cursor_type == CursorType.INTEGER:
        typed_merged: tuple[MicrobatchInterval, ...] | None = _merge_typed_integers(
            intervals=intervals
        )
        if typed_merged is not None:
            return typed_merged
    ordered: tuple[MicrobatchInterval, ...] = tuple(
        sorted(
            intervals,
            key=lambda interval: cursor_sort_key(raw=interval.start, cursor_type=cursor_type),
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


def _lt(*, left: str, right: str, cursor_type: str) -> bool:
    return (
        compare(
            left=parse(raw=left, cursor_type=cursor_type),
            right=parse(raw=right, cursor_type=cursor_type),
        )
        < 0
    )


def _merge_typed_integers(
    *, intervals: tuple[MicrobatchInterval, ...]
) -> tuple[MicrobatchInterval, ...] | None:
    typed: list[AlignedInterval] = []
    for interval in intervals:
        start: CursorScalar = parse(raw=interval.start, cursor_type=CursorType.INTEGER)
        end: CursorScalar = parse(raw=interval.end, cursor_type=CursorType.INTEGER)
        if (
            not isinstance(start, IntegerValue)
            or not isinstance(end, IntegerValue)
            or render(value=start) != interval.start
            or render(value=end) != interval.end
            or start.value >= end.value
        ):
            return None
        typed.append(AlignedInterval(start=start, end=end, grain=None))
    return tuple(
        MicrobatchInterval(start=render(value=interval.start), end=render(value=interval.end))
        for interval in merge(intervals=tuple(typed))
    )
