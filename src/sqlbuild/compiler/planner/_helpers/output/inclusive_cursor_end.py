"""Single source of truth for converting between inclusive and exclusive cursor end bounds."""

from __future__ import annotations

from datetime import datetime

from sqlbuild.compiler.planner.constants import WHOLE_DAY_CURSOR_GRAINS
from sqlbuild.compiler.planner.models import CursorBounds
from sqlbuild.compiler.planner.types import CursorGrain, CursorType
from sqlbuild.cursor_algebra.main.exclusive_to_inclusive import exclusive_to_inclusive
from sqlbuild.cursor_algebra.main.inclusive_to_exclusive import inclusive_to_exclusive
from sqlbuild.cursor_algebra.main.observed_partition import observed_partition
from sqlbuild.cursor_algebra.main.render import render
from sqlbuild.cursor_algebra.main.try_parse import try_parse
from sqlbuild.cursor_algebra.models import AlignedInterval, TimestampValue
from sqlbuild.cursor_algebra.types import CursorScalar


def discovered_cursor_partition(
    *, value: object, cursor_type: str | None, cursor_grain: str | None
) -> tuple[object, object]:
    """Return the grain-aligned partition containing one observed physical value."""

    if cursor_type not in {CursorType.INTEGER, CursorType.TIMESTAMP}:
        return value, value
    parsed: CursorScalar | None = try_parse(raw=value, cursor_type=cursor_type)
    if parsed is None:
        return value, value
    grain: CursorGrain | None = (
        None
        if cursor_type == CursorType.INTEGER
        else CursorGrain(
            cursor_grain
            or (CursorGrain.SECOND if isinstance(parsed, TimestampValue) else CursorGrain.DAY)
        )
    )
    partition: AlignedInterval = observed_partition(value=parsed, grain=grain)
    if isinstance(value, str):
        return render(value=partition.start), render(value=partition.end)
    return partition.start.value, partition.end.value


def advance_discovered_cursor_end(
    *, value: object, cursor_type: str | None, cursor_grain: str | None
) -> object:
    """Convert an observed physical maximum to its exclusive partition end."""

    return discovered_cursor_partition(
        value=value,
        cursor_type=cursor_type,
        cursor_grain=cursor_grain,
    )[1]


def advance_cursor_end(
    *,
    value: str,
    cursor_type: str | None,
    cursor_grain: str | None,
) -> str:
    """Return the exclusive stored bound for an inclusive end value (adds one step)."""

    effective_type: str = cursor_type or CursorType.TIMESTAMP
    parsed: CursorScalar | None = try_parse(raw=value, cursor_type=effective_type)
    if parsed is None:
        return value
    grain: CursorGrain | None = (
        None
        if effective_type == CursorType.INTEGER
        else CursorGrain(cursor_grain or CursorGrain.SECOND)
    )
    return render(value=inclusive_to_exclusive(value=parsed, grain=grain))


def inclusive_cursor_end(
    *,
    end: str,
    cursor_type: str | None,
    cursor_grain: str | None,
) -> str:
    """Return the last cursor value included by an exclusive end bound."""

    effective_type: str = cursor_type or CursorType.TIMESTAMP
    parsed: CursorScalar | None = try_parse(raw=end, cursor_type=effective_type)
    if parsed is None:
        return end
    grain: CursorGrain | None = (
        None
        if effective_type == CursorType.INTEGER
        else CursorGrain(cursor_grain or CursorGrain.SECOND)
    )
    return render(value=exclusive_to_inclusive(value=parsed, grain=grain))


def cursor_bound_display(
    *,
    value: str,
    cursor_type: str | None,
    cursor_grain: str | None,
) -> str:
    """Render a cursor bound for display, collapsing a whole-day midnight timestamp to a date."""

    if cursor_type == CursorType.INTEGER:
        return value
    try:
        parsed: datetime = datetime.fromisoformat(value)
    except ValueError:
        return value
    if cursor_grain in WHOLE_DAY_CURSOR_GRAINS and _has_no_time_component(value=parsed):
        return parsed.date().isoformat()
    return value


def resolve_bounded_cursor_override(
    *,
    start_cursor_override: str | None,
    end_cursor_override: str | None,
    cursor_type: str | None,
    cursor_grain: str | None,
) -> CursorBounds | None:
    """Resolve a fully bounded inclusive operator override to an executable interval."""

    if start_cursor_override is None or end_cursor_override is None:
        return None
    effective_type: str = cursor_type or CursorType.TIMESTAMP
    start: CursorScalar | None = try_parse(raw=start_cursor_override, cursor_type=effective_type)
    exclusive_end: CursorScalar | None = try_parse(
        raw=advance_cursor_end(
            value=end_cursor_override,
            cursor_type=cursor_type,
            cursor_grain=cursor_grain,
        ),
        cursor_type=effective_type,
    )
    if start is None or exclusive_end is None:
        return None
    return CursorBounds(
        start=start,
        end=exclusive_end,
    )


def _has_no_time_component(*, value: datetime) -> bool:
    return (value.hour, value.minute, value.second, value.microsecond) == (0, 0, 0, 0)
