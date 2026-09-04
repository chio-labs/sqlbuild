"""Private typed cursor comparison helpers."""

from datetime import UTC, datetime

from sqlbuild.cursor_algebra._helpers.parsing import parse_scalar
from sqlbuild.cursor_algebra.exceptions import CursorAlgebraError
from sqlbuild.cursor_algebra.models import DateValue, IntegerValue, TimestampValue
from sqlbuild.cursor_algebra.types import CursorScalar


def comparison_value(*, value: CursorScalar) -> datetime | int:
    """Project a cursor scalar into a sortable domain."""

    if isinstance(value, IntegerValue):
        return value.value
    if isinstance(value, DateValue):
        return datetime.combine(value.value, datetime.min.time())
    timestamp: datetime = value.value
    if timestamp.tzinfo is not None:
        return timestamp.astimezone(UTC).replace(tzinfo=None)
    return timestamp


def compare_scalars(*, left: CursorScalar, right: CursorScalar) -> int:
    """Compare two compatible cursor scalars."""

    left_value: datetime | int = comparison_value(value=left)
    right_value: datetime | int = comparison_value(value=right)
    if isinstance(left_value, int) and isinstance(right_value, int):
        return (left_value > right_value) - (left_value < right_value)
    if isinstance(left_value, datetime) and isinstance(right_value, datetime):
        return (left_value > right_value) - (left_value < right_value)
    raise CursorAlgebraError("cannot compare temporal and integer cursor values")


def as_scalar(*, raw: object, cursor_type: str) -> CursorScalar:
    """Return a typed value unchanged or parse its boundary representation."""

    if isinstance(raw, TimestampValue | DateValue | IntegerValue):
        return raw
    return parse_scalar(raw=raw, cursor_type=cursor_type)
