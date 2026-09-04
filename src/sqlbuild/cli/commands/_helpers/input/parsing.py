"""Neutral command input conversion."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlbuild.cursor_algebra.exceptions import CursorAlgebraError
from sqlbuild.cursor_algebra.models import DateValue, IntegerValue, TimestampValue
from sqlbuild.cursor_algebra.types import CursorScalar


def parse_cursor_timestamp(value: str | CursorScalar | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, TimestampValue):
        return value.value
    if isinstance(value, DateValue):
        return datetime.combine(value.value, datetime.min.time())
    if isinstance(value, IntegerValue):
        raise CursorAlgebraError("an integer cursor cannot be used as a timestamp")
    return datetime.fromisoformat(value)


def parse_cursor_integer(value: str | CursorScalar | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, IntegerValue):
        return value.value
    if isinstance(value, DateValue | TimestampValue):
        raise CursorAlgebraError("a timestamp cursor cannot be used as an integer")
    return int(Decimal(value))
