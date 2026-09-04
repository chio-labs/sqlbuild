"""Single source of truth for converting between inclusive and exclusive cursor end bounds."""

from __future__ import annotations

from datetime import datetime

from sqlbuild.compiler.planner.constants import WHOLE_DAY_CURSOR_GRAINS
from sqlbuild.compiler.planner.models import CursorBounds
from sqlbuild.compiler.planner.types import CursorGrain, CursorType
from sqlbuild.cursor_algebra.main.exclusive_to_inclusive import exclusive_to_inclusive
from sqlbuild.cursor_algebra.main.inclusive_to_exclusive import inclusive_to_exclusive
from sqlbuild.cursor_algebra.main.render import render
from sqlbuild.cursor_algebra.main.try_parse import try_parse
from sqlbuild.cursor_algebra.types import CursorScalar


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
    inclusive_end: CursorScalar | None = try_parse(
        raw=end_cursor_override, cursor_type=effective_type
    )
    if start is None or inclusive_end is None:
        return None
    grain: CursorGrain | None = (
        None
        if effective_type == CursorType.INTEGER
        else CursorGrain(cursor_grain or CursorGrain.SECOND)
    )
    return CursorBounds(
        start=start,
        end=inclusive_to_exclusive(value=inclusive_end, grain=grain),
    )


def _has_no_time_component(*, value: datetime) -> bool:
    return (value.hour, value.minute, value.second, value.microsecond) == (0, 0, 0, 0)
