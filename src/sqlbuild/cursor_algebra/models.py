"""Immutable cursor algebra values."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from sqlbuild.compiler.planner.types import CursorGrain
from sqlbuild.cursor_algebra.exceptions import CursorAlgebraError


@dataclass(frozen=True, kw_only=True)
class TimestampValue:
    """Timestamp cursor value; the datetime retains its original UTC offset."""

    value: datetime
    source_text: str | None = field(default=None, compare=False, repr=False)


@dataclass(frozen=True, kw_only=True)
class DateValue:
    """Date cursor value which must remain date-formatted when rendered."""

    value: date


@dataclass(frozen=True, kw_only=True)
class IntegerValue:
    """Integral cursor value."""

    value: int


@dataclass(frozen=True, kw_only=True)
class AlignedInterval:
    """Validated half-open cursor interval."""

    start: TimestampValue | DateValue | IntegerValue
    end: TimestampValue | DateValue | IntegerValue
    grain: CursorGrain | None

    def __post_init__(self) -> None:
        from sqlbuild.cursor_algebra.main.compare import compare
        from sqlbuild.cursor_algebra.main.floor_to_grain import floor_to_grain

        if compare(left=self.start, right=self.end) >= 0:
            raise CursorAlgebraError("cursor interval start must be less than end")
        if self.grain is None:
            if not isinstance(self.start, IntegerValue) or not isinstance(self.end, IntegerValue):
                raise CursorAlgebraError("temporal cursor intervals require a grain")
            return
        if floor_to_grain(value=self.start, grain=self.grain) != self.start:
            raise CursorAlgebraError("cursor interval start must be grain-aligned")
        if floor_to_grain(value=self.end, grain=self.grain) != self.end:
            raise CursorAlgebraError("cursor interval end must be grain-aligned")
