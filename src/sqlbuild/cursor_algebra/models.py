"""Immutable cursor algebra values."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import ClassVar

from sqlbuild.compiler.planner.types import CursorGrain
from sqlbuild.cursor_algebra.constants import (
    DURATION_DAY_UNIT,
    DURATION_HOUR_UNIT,
    DURATION_MINUTE_UNIT,
    DURATION_MONTH_UNIT,
    DURATION_SECOND_UNIT,
    DURATION_YEAR_UNIT,
)
from sqlbuild.cursor_algebra.exceptions import CursorAlgebraError


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


@dataclass(frozen=True)
class Duration:
    """A calendar-aware duration (years/months plus fixed time units)."""

    _PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?:(\d+)y)?(?:(\d+)mo)?(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$"
    )
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

        match: re.Match[str] | None = cls._PATTERN.match(value)
        if match is None:
            return None
        duration: Duration = cls(
            years=int(match.group(1) or 0),
            months=int(match.group(2) or 0),
            days=int(match.group(3) or 0),
            hours=int(match.group(4) or 0),
            minutes=int(match.group(5) or 0),
            seconds=int(match.group(6) or 0),
        )
        if duration.is_zero:
            return None
        return duration

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

    @property
    def _fixed_timedelta(self) -> timedelta:
        return timedelta(
            days=self.days, hours=self.hours, minutes=self.minutes, seconds=self.seconds
        )

    def add_to(self, moment: datetime) -> datetime:
        """Return the moment advanced by this duration."""

        return (
            self._shift_months(moment=moment, months_delta=self.total_months)
            + self._fixed_timedelta
        )

    def subtract_from(self, moment: datetime) -> datetime:
        """Return the moment moved back by this duration."""

        return (
            self._shift_months(moment=moment, months_delta=-self.total_months)
            - self._fixed_timedelta
        )

    def _shift_months(self, *, moment: datetime, months_delta: int) -> datetime:
        if months_delta == 0:
            return moment
        total: int = (moment.year * self._MONTHS_PER_YEAR + (moment.month - 1)) + months_delta
        year: int = total // self._MONTHS_PER_YEAR
        month: int = total % self._MONTHS_PER_YEAR + 1
        day: int = min(moment.day, calendar.monthrange(year, month)[1])
        return moment.replace(year=year, month=month, day=day)
