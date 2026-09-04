"""Private scalar arithmetic primitives."""

from datetime import date, datetime, timedelta

from sqlbuild.compiler.planner.types import CursorGrain
from sqlbuild.cursor_algebra.constants import GRAIN_FIXED_STEP
from sqlbuild.cursor_algebra.exceptions import CursorAlgebraError
from sqlbuild.cursor_algebra.models import DateValue, IntegerValue, TimestampValue
from sqlbuild.cursor_algebra.types import CursorScalar

_FINAL_MONTH: int = 12


def floor_scalar(*, value: CursorScalar, grain: CursorGrain) -> CursorScalar:
    """Floor one scalar without crossing the serialization boundary."""

    if isinstance(value, IntegerValue):
        return value
    if isinstance(value, DateValue):
        plain_date: date = value.value
        if grain == CursorGrain.MONTH:
            return DateValue(value=plain_date.replace(day=1))
        if grain == CursorGrain.YEAR:
            return DateValue(value=plain_date.replace(month=1, day=1))
        return value
    timestamp: datetime = value.value
    if grain == CursorGrain.SECOND:
        timestamp = timestamp.replace(microsecond=0)
    elif grain == CursorGrain.MINUTE:
        timestamp = timestamp.replace(second=0, microsecond=0)
    elif grain == CursorGrain.HOUR:
        timestamp = timestamp.replace(minute=0, second=0, microsecond=0)
    elif grain == CursorGrain.DAY:
        timestamp = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
    elif grain == CursorGrain.MONTH:
        timestamp = timestamp.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif grain == CursorGrain.YEAR:
        timestamp = timestamp.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return TimestampValue(value=timestamp)


def advance_scalar(*, value: CursorScalar, grain: CursorGrain) -> CursorScalar:
    """Advance one aligned scalar by one grain."""

    if isinstance(value, IntegerValue):
        return IntegerValue(value=value.value + 1)
    if isinstance(value, DateValue) and grain not in {
        CursorGrain.MONTH,
        CursorGrain.YEAR,
    }:
        return DateValue(value=value.value + timedelta(days=1))
    fixed_step: timedelta | None = GRAIN_FIXED_STEP[grain]
    raw: date | datetime = value.value
    if fixed_step is not None:
        advanced: date | datetime = raw + fixed_step
    elif grain == CursorGrain.MONTH:
        advanced = raw.replace(
            year=raw.year + (1 if raw.month == _FINAL_MONTH else 0),
            month=1 if raw.month == _FINAL_MONTH else raw.month + 1,
            day=1,
        )
    else:
        advanced = raw.replace(year=raw.year + 1, month=1, day=1)
    if isinstance(value, TimestampValue) and isinstance(advanced, datetime):
        return TimestampValue(value=advanced)
    if isinstance(advanced, datetime):
        return DateValue(value=advanced.date())
    return DateValue(value=advanced)


def advance_scalar_by(
    *, value: CursorScalar, grain: CursorGrain | None, steps: int
) -> CursorScalar:
    """Advance an aligned scalar by many grain units in constant time."""

    if isinstance(value, IntegerValue):
        return IntegerValue(value=value.value + steps)
    if grain is None:
        raise CursorAlgebraError("temporal cursor values require a grain")
    if isinstance(value, DateValue):
        if grain == CursorGrain.MONTH:
            return DateValue(value=_advance_months(value=value.value, steps=steps))
        if grain == CursorGrain.YEAR:
            return DateValue(value=value.value.replace(year=value.value.year + steps))
        return DateValue(value=value.value + timedelta(days=steps))
    if grain == CursorGrain.MONTH:
        advanced_month: date | datetime = _advance_months(value=value.value, steps=steps)
        if not isinstance(advanced_month, datetime):
            raise CursorAlgebraError("timestamp month advancement lost timestamp representation")
        return TimestampValue(value=advanced_month)
    if grain == CursorGrain.YEAR:
        return TimestampValue(value=value.value.replace(year=value.value.year + steps))
    fixed_step: timedelta | None = GRAIN_FIXED_STEP[grain]
    if fixed_step is None:
        raise CursorAlgebraError(f"cursor grain has no fixed step: {grain}")
    return TimestampValue(value=value.value + fixed_step * steps)


def _advance_months(*, value: date | datetime, steps: int) -> date | datetime:
    month_index: int = value.year * _FINAL_MONTH + value.month - 1 + steps
    year, zero_based_month = divmod(month_index, _FINAL_MONTH)
    return value.replace(year=year, month=zero_based_month + 1, day=1)
