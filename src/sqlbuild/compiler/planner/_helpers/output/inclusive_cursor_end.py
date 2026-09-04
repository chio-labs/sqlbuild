"""Single source of truth for converting between inclusive and exclusive cursor end bounds."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import cast

from sqlbuild.compiler.planner.constants import WHOLE_DAY_CURSOR_GRAINS
from sqlbuild.compiler.planner.models import CursorBounds
from sqlbuild.compiler.planner.types import CursorGrain, CursorType


def discovered_cursor_partition(
    *, value: object, cursor_type: str | None, cursor_grain: str | None
) -> tuple[object, object]:
    """Return the grain-aligned partition containing one observed physical value."""

    if cursor_type == CursorType.INTEGER:
        return _discovered_integer_partition(value=value)
    if cursor_type != CursorType.TIMESTAMP:
        return value, value
    parsed, was_string = _parse_discovered_timestamp(value=value)
    if parsed is None:
        return value, value
    grain: str = cursor_grain or (
        CursorGrain.SECOND if isinstance(parsed, datetime) else CursorGrain.DAY
    )
    start: date | datetime = _floor_discovered_timestamp(value=parsed, grain=grain)
    end: date | datetime = _advance_discovered_timestamp(value=start, grain=grain)
    if not was_string:
        return start, end
    return _format_discovered_timestamp(value=start), _format_discovered_timestamp(value=end)


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

    if cursor_type == CursorType.INTEGER:
        return _advance_integer_end(value=value)
    return _advance_timestamp_end(value=value, cursor_grain=cursor_grain)


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
    return CursorBounds(
        start=start_cursor_override,
        end=advance_cursor_end(
            value=end_cursor_override,
            cursor_type=cursor_type,
            cursor_grain=cursor_grain,
        ),
    )


def _advance_integer_end(*, value: str) -> str:
    try:
        return str(int(Decimal(value)) + 1)
    except (InvalidOperation, ValueError):
        return value


def _inclusive_integer_end(*, end: str) -> str:
    try:
        return str(int(Decimal(end)) - 1)
    except (InvalidOperation, ValueError):
        return end


def _advance_timestamp_end(*, value: str, cursor_grain: str | None) -> str:
    plain_date: date | None = _try_parse_plain_date(value=value)
    if plain_date is not None:
        return (plain_date + timedelta(days=1)).isoformat()
    try:
        parsed: datetime = datetime.fromisoformat(value)
    except ValueError:
        return value
    return (parsed + _grain_step(cursor_grain=cursor_grain)).isoformat()


def _inclusive_timestamp_end(*, end: str, cursor_grain: str | None) -> str:
    plain_date: date | None = _try_parse_plain_date(value=end)
    if plain_date is not None:
        return (plain_date - timedelta(days=1)).isoformat()
    try:
        parsed: datetime = datetime.fromisoformat(end)
    except ValueError:
        return end
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


def _try_parse_plain_date(*, value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _discovered_integer_partition(*, value: object) -> tuple[object, object]:
    try:
        parsed: Decimal = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return value, value
    if parsed != int(parsed):
        return value, value
    start: int = int(parsed)
    if isinstance(value, str):
        return str(start), str(start + 1)
    return start, start + 1


def _parse_discovered_timestamp(*, value: object) -> tuple[date | datetime | None, bool]:
    if isinstance(value, datetime):
        return value, False
    if isinstance(value, date):
        return value, False
    if not isinstance(value, str):
        return None, False
    try:
        return date.fromisoformat(value), True
    except ValueError:
        try:
            return datetime.fromisoformat(value), True
        except ValueError:
            return None, True


def _floor_discovered_timestamp(*, value: date | datetime, grain: str) -> date | datetime:
    if isinstance(value, datetime):
        if grain == CursorGrain.SECOND:
            return value.replace(microsecond=0)
        if grain == CursorGrain.MINUTE:
            return value.replace(second=0, microsecond=0)
        if grain == CursorGrain.HOUR:
            return value.replace(minute=0, second=0, microsecond=0)
        if grain == CursorGrain.DAY:
            return value.replace(hour=0, minute=0, second=0, microsecond=0)
        if grain == CursorGrain.MONTH:
            return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if grain == CursorGrain.YEAR:
            return value.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return value
    if grain == CursorGrain.MONTH:
        return value.replace(day=1)
    if grain == CursorGrain.YEAR:
        return value.replace(month=1, day=1)
    if grain in {CursorGrain.SECOND, CursorGrain.MINUTE, CursorGrain.HOUR}:
        return datetime.combine(value, time.min)
    return value


def _advance_discovered_timestamp(*, value: date | datetime, grain: str) -> date | datetime:
    if grain == CursorGrain.SECOND:
        return value + timedelta(seconds=1)
    if grain == CursorGrain.MINUTE:
        return value + timedelta(minutes=1)
    if grain == CursorGrain.HOUR:
        return value + timedelta(hours=1)
    if grain == CursorGrain.DAY:
        return value + timedelta(days=1)
    if grain == CursorGrain.MONTH:
        final_month: int = 12
        year: int = value.year + (1 if value.month == final_month else 0)
        month: int = 1 if value.month == final_month else value.month + 1
        return value.replace(year=year, month=month, day=1)
    if grain == CursorGrain.YEAR:
        return value.replace(year=value.year + 1, month=1, day=1)
    return value


def _format_discovered_timestamp(*, value: date | datetime) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return cast(date, value).isoformat()
