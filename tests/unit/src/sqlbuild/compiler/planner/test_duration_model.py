from __future__ import annotations

from datetime import datetime

import pytest

from sqlbuild.compiler.planner.models import Duration
from tests.unit.src.sqlbuild.compiler.planner._test_types import (
    DurationParseNoneTestCase,
    DurationParseTestCase,
    DurationShiftTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DurationParseTestCase(
            description="single month",
            value="1mo",
            expected_years=0,
            expected_months=1,
            expected_days=0,
            expected_hours=0,
            expected_minutes=0,
            expected_seconds=0,
            expected_has_calendar_component=True,
            expected_fixed_seconds=0,
        ),
        DurationParseTestCase(
            description="two months",
            value="2mo",
            expected_years=0,
            expected_months=2,
            expected_days=0,
            expected_hours=0,
            expected_minutes=0,
            expected_seconds=0,
            expected_has_calendar_component=True,
            expected_fixed_seconds=0,
        ),
        DurationParseTestCase(
            description="year and months combined",
            value="1y6mo",
            expected_years=1,
            expected_months=6,
            expected_days=0,
            expected_hours=0,
            expected_minutes=0,
            expected_seconds=0,
            expected_has_calendar_component=True,
            expected_fixed_seconds=0,
        ),
        DurationParseTestCase(
            description="thirty days is fixed length",
            value="30d",
            expected_years=0,
            expected_months=0,
            expected_days=30,
            expected_hours=0,
            expected_minutes=0,
            expected_seconds=0,
            expected_has_calendar_component=False,
            expected_fixed_seconds=30 * 86_400,
        ),
        DurationParseTestCase(
            description="hours minutes seconds",
            value="1h30m15s",
            expected_years=0,
            expected_months=0,
            expected_days=0,
            expected_hours=1,
            expected_minutes=30,
            expected_seconds=15,
            expected_has_calendar_component=False,
            expected_fixed_seconds=3_600 + 30 * 60 + 15,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_duration_string_when_parsing_then_matches_expected_components(
    test_case: DurationParseTestCase,
) -> None:
    duration: Duration | None = Duration.parse(test_case.value)

    assert duration is not None
    assert duration.years == test_case.expected_years
    assert duration.months == test_case.expected_months
    assert duration.days == test_case.expected_days
    assert duration.hours == test_case.expected_hours
    assert duration.minutes == test_case.expected_minutes
    assert duration.seconds == test_case.expected_seconds
    assert duration.has_calendar_component == test_case.expected_has_calendar_component
    assert duration.fixed_seconds == test_case.expected_fixed_seconds


@pytest.mark.parametrize(
    "test_case",
    [
        DurationParseNoneTestCase(
            description="empty string is not a duration",
            value="",
            expected_is_none=True,
        ),
        DurationParseNoneTestCase(
            description="bare integer is not a duration",
            value="1000",
            expected_is_none=True,
        ),
        DurationParseNoneTestCase(
            description="unknown unit is not a duration",
            value="5w",
            expected_is_none=True,
        ),
        DurationParseNoneTestCase(
            description="zero duration is treated as absent",
            value="0d",
            expected_is_none=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_non_duration_string_when_parsing_then_returns_none(
    test_case: DurationParseNoneTestCase,
) -> None:
    duration: Duration | None = Duration.parse(test_case.value)

    assert (duration is None) == test_case.expected_is_none


@pytest.mark.parametrize(
    "test_case",
    [
        DurationShiftTestCase(
            description="one month across a month boundary",
            value="1mo",
            moment="2014-01-01T00:00:00",
            expected_added="2014-02-01T00:00:00",
            expected_subtracted="2013-12-01T00:00:00",
        ),
        DurationShiftTestCase(
            description="one month clamps day to end of a shorter month",
            value="1mo",
            moment="2014-01-31T00:00:00",
            expected_added="2014-02-28T00:00:00",
            expected_subtracted="2013-12-31T00:00:00",
        ),
        DurationShiftTestCase(
            description="two months rolls across a year boundary",
            value="2mo",
            moment="2014-12-01T00:00:00",
            expected_added="2015-02-01T00:00:00",
            expected_subtracted="2014-10-01T00:00:00",
        ),
        DurationShiftTestCase(
            description="one year",
            value="1y",
            moment="2016-02-29T00:00:00",
            expected_added="2017-02-28T00:00:00",
            expected_subtracted="2015-02-28T00:00:00",
        ),
        DurationShiftTestCase(
            description="fixed thirty days is not calendar aware",
            value="30d",
            moment="2014-01-01T00:00:00",
            expected_added="2014-01-31T00:00:00",
            expected_subtracted="2013-12-02T00:00:00",
        ),
        DurationShiftTestCase(
            description="calendar and fixed components combine",
            value="1mo1d",
            moment="2014-01-31T12:00:00",
            expected_added="2014-03-01T12:00:00",
            expected_subtracted="2013-12-30T12:00:00",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_duration_when_shifting_a_moment_then_matches_expected(
    test_case: DurationShiftTestCase,
) -> None:
    duration: Duration | None = Duration.parse(test_case.value)
    moment: datetime = datetime.fromisoformat(test_case.moment)

    assert duration is not None
    assert duration.add_to(moment).isoformat() == test_case.expected_added
    assert duration.subtract_from(moment).isoformat() == test_case.expected_subtracted
