from __future__ import annotations

import pytest

from sqlbuild.compiler.planner._helpers.output.inclusive_cursor_end import (
    advance_cursor_end,
    inclusive_cursor_end,
)
from sqlbuild.compiler.planner.types import CursorGrain, CursorType
from tests.unit.src.sqlbuild.compiler.planner.main._test_types import (
    AdvanceCursorEndTestCase,
    CursorEndRoundTripTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        AdvanceCursorEndTestCase(
            description="day grain date value steps forward one whole day",
            value="2014-12-31",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.DAY,
            expected_end="2015-01-01",
        ),
        AdvanceCursorEndTestCase(
            description="midnight timestamp value steps forward one whole day",
            value="2014-12-31T00:00:00",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.DAY,
            expected_end="2015-01-01T00:00:00",
        ),
        AdvanceCursorEndTestCase(
            description="date value without a grain steps forward one whole day",
            value="2026-04-24",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=None,
            expected_end="2026-04-25",
        ),
        AdvanceCursorEndTestCase(
            description="timestamp value without a grain steps forward one second",
            value="2014-12-31T11:59:59",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=None,
            expected_end="2014-12-31T12:00:00",
        ),
        AdvanceCursorEndTestCase(
            description="hour grain timestamp value steps forward one hour",
            value="2014-12-31T11:00:00",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.HOUR,
            expected_end="2014-12-31T12:00:00",
        ),
        AdvanceCursorEndTestCase(
            description="hour grain midnight timestamp steps forward one hour not one day",
            value="2014-12-31T00:00:00",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.HOUR,
            expected_end="2014-12-31T01:00:00",
        ),
        AdvanceCursorEndTestCase(
            description="midnight timestamp without grain steps forward one second",
            value="2014-12-31T00:00:00",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=None,
            expected_end="2014-12-31T00:00:01",
        ),
        AdvanceCursorEndTestCase(
            description="integer value steps forward one unit",
            value="200",
            cursor_type=CursorType.INTEGER,
            cursor_grain=None,
            expected_end="201",
        ),
        AdvanceCursorEndTestCase(
            description="unparsable value is returned unchanged",
            value="__SQB_CURSOR_END__",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=None,
            expected_end="__SQB_CURSOR_END__",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_inclusive_value_when_advancing_then_returns_exclusive_bound(
    test_case: AdvanceCursorEndTestCase,
) -> None:
    result: str = advance_cursor_end(
        value=test_case.value,
        cursor_type=test_case.cursor_type,
        cursor_grain=test_case.cursor_grain,
    )

    assert result == test_case.expected_end


@pytest.mark.parametrize(
    "test_case",
    [
        CursorEndRoundTripTestCase(
            description="day grain date round-trips through advance then inclusive",
            inclusive_value="2014-12-31",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.DAY,
            expected_round_trip="2014-12-31",
        ),
        CursorEndRoundTripTestCase(
            description="month grain date round-trips through advance then inclusive",
            inclusive_value="2014-12-31",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.MONTH,
            expected_round_trip="2014-12-31",
        ),
        CursorEndRoundTripTestCase(
            description="hour grain timestamp round-trips through advance then inclusive",
            inclusive_value="2014-12-31T12:00:00",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.HOUR,
            expected_round_trip="2014-12-31T12:00:00",
        ),
        CursorEndRoundTripTestCase(
            description="second grain timestamp round-trips through advance then inclusive",
            inclusive_value="2014-12-31T12:00:00",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=None,
            expected_round_trip="2014-12-31T12:00:00",
        ),
        CursorEndRoundTripTestCase(
            description="integer round-trips through advance then inclusive",
            inclusive_value="200",
            cursor_type=CursorType.INTEGER,
            cursor_grain=None,
            expected_round_trip="200",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_inclusive_value_when_advancing_then_inclusive_end_is_exact_inverse(
    test_case: CursorEndRoundTripTestCase,
) -> None:
    exclusive_bound: str = advance_cursor_end(
        value=test_case.inclusive_value,
        cursor_type=test_case.cursor_type,
        cursor_grain=test_case.cursor_grain,
    )

    round_tripped: str = inclusive_cursor_end(
        end=exclusive_bound,
        cursor_type=test_case.cursor_type,
        cursor_grain=test_case.cursor_grain,
    )

    assert round_tripped == test_case.expected_round_trip
