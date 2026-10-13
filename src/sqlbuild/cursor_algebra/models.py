"""Immutable cursor algebra values."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import ClassVar

from sqlbuild._native import (
    parse_cursor_duration,
    shift_by_cursor_duration,
    validate_cursor_interval,
)
from sqlbuild.compiler.planner.types import CursorGrain
from sqlbuild.cursor_algebra.constants import (
    DURATION_DAY_UNIT,
    DURATION_HOUR_UNIT,
    DURATION_MINUTE_UNIT,
    DURATION_MONTH_UNIT,
    DURATION_SECOND_UNIT,
    DURATION_YEAR_UNIT,
)


@dataclass(frozen=True, kw_only=True)
class TimestampValue:
    """Timestamp cursor value; aware datetimes are normalized to UTC at ingestion."""

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
        validate_cursor_interval(start=self.start, end=self.end, grain=self.grain)


@dataclass(frozen=True)
class Duration:
    """A calendar-aware duration (years/months plus fixed time units)."""

    _MONTHS_PER_YEAR: ClassVar[int] = 12
    _SECONDS_PER_DAY: ClassVar[int] = 86_400
    _SECONDS_PER_HOUR: ClassVar[int] = 3_600
    _SECONDS_PER_MINUTE: ClassVar[int] = 60

    years: int = 0
    months: int = 0
    days: int = 0
    hours: int = 0
    minutes: int = 0
    seconds: int = 0

    @classmethod
    def parse(cls, value: str) -> Duration | None:
        """Parse a string like '1mo', '1y6mo', '30d', or '6h' into a duration."""

        parts: tuple[int, int, int, int, int, int] | None = parse_cursor_duration(value)
        if parts is None:
            return None
        years, months, days, hours, minutes, seconds = parts
        return cls(
            years=years, months=months, days=days, hours=hours, minutes=minutes, seconds=seconds
        )

    @property
    def is_zero(self) -> bool:
        """Return whether the duration is empty."""

        return self.total_months == 0 and self.fixed_seconds == 0

    @property
    def units(self) -> frozenset[str]:
        """Return the unit suffixes with non-zero values."""

        values_by_unit: tuple[tuple[str, int], ...] = (
            (DURATION_YEAR_UNIT, self.years),
            (DURATION_MONTH_UNIT, self.months),
            (DURATION_DAY_UNIT, self.days),
            (DURATION_HOUR_UNIT, self.hours),
            (DURATION_MINUTE_UNIT, self.minutes),
            (DURATION_SECOND_UNIT, self.seconds),
        )
        return frozenset(unit for unit, amount in values_by_unit if amount != 0)

    def is_single_unit_in(self, allowed_units: frozenset[str]) -> bool:
        """Return whether exactly one used unit belongs to the allowed vocabulary."""

        return len(self.units) == 1 and self.units <= allowed_units

    @property
    def has_calendar_component(self) -> bool:
        """Return whether the duration includes variable-length years or months."""

        return self.total_months != 0

    @property
    def fixed_seconds(self) -> int:
        """Return the fixed-length portion (days and below) as whole seconds."""

        return (
            self.days * self._SECONDS_PER_DAY
            + self.hours * self._SECONDS_PER_HOUR
            + self.minutes * self._SECONDS_PER_MINUTE
            + self.seconds
        )

    @property
    def total_months(self) -> int:
        """Return the whole-month portion (years folded into months)."""

        return self.years * self._MONTHS_PER_YEAR + self.months

    def add_to(self, moment: datetime) -> datetime:
        """Return the moment advanced by this duration."""

        return shift_by_cursor_duration(moment=moment, duration=self, direction=1)

    def subtract_from(self, moment: datetime) -> datetime:
        """Return the moment moved back by this duration."""

        return shift_by_cursor_duration(moment=moment, duration=self, direction=-1)
