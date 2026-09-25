"""Cursor algebra enums and type aliases."""

from enum import StrEnum

from sqlbuild.cursor_algebra.models import DateValue, IntegerValue, TimestampValue

type CursorScalar = TimestampValue | DateValue | IntegerValue


class BoundSentinel(StrEnum):
    """Typed cursor sentinel used before SQL-boundary substitution."""

    START = "__SQB_CURSOR_START__"
    END = "__SQB_CURSOR_END__"


type Bound = CursorScalar | BoundSentinel
