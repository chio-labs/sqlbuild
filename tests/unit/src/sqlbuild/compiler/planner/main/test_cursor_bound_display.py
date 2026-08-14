from __future__ import annotations

import pytest

from sqlbuild.compiler.planner._helpers.output.inclusive_cursor_end import cursor_bound_display
from sqlbuild.compiler.planner.types import CursorGrain, CursorType
from tests.unit.src.sqlbuild.compiler.planner.main._test_types import (
    CursorBoundDisplayTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CursorBoundDisplayTestCase(
            description="day grain midnight timestamp collapses to a bare date",
            value="2014-01-01T00:00:00",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.DAY,
            expected_display="2014-01-01",
        ),
        CursorBoundDisplayTestCase(
            description="month grain midnight timestamp collapses to a bare date",
            value="2014-01-01T00:00:00",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.MONTH,
            expected_display="2014-01-01",
        ),
        CursorBoundDisplayTestCase(
            description="day grain bare date is unchanged",
            value="2014-01-01",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.DAY,
            expected_display="2014-01-01",
        ),
        CursorBoundDisplayTestCase(
            description="day grain timestamp with a time component keeps the time",
            value="2014-01-01T06:30:00",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.DAY,
            expected_display="2014-01-01T06:30:00",
        ),
        CursorBoundDisplayTestCase(
            description="hour grain midnight timestamp keeps the time",
            value="2014-01-01T00:00:00",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.HOUR,
            expected_display="2014-01-01T00:00:00",
        ),
        CursorBoundDisplayTestCase(
            description="timestamp without a grain keeps the time",
            value="2014-01-01T00:00:00",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=None,
            expected_display="2014-01-01T00:00:00",
        ),
        CursorBoundDisplayTestCase(
            description="integer bound is unchanged",
            value="200",
            cursor_type=CursorType.INTEGER,
            cursor_grain=None,
            expected_display="200",
        ),
        CursorBoundDisplayTestCase(
            description="unparsable bound is unchanged",
            value="__SQB_CURSOR_START__",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.DAY,
            expected_display="__SQB_CURSOR_START__",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cursor_bound_when_formatting_for_display_then_matches_expected(
    test_case: CursorBoundDisplayTestCase,
) -> None:
    result: str = cursor_bound_display(
        value=test_case.value,
        cursor_type=test_case.cursor_type,
        cursor_grain=test_case.cursor_grain,
    )

    assert result == test_case.expected_display
