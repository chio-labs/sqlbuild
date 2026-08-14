from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.main.execution.inclusive_cursor_end import inclusive_cursor_end
from sqlbuild.compiler.planner.types import CursorGrain, CursorType
from tests.unit.src.sqlbuild.compiler.planner.main._test_types import InclusiveCursorEndTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        InclusiveCursorEndTestCase(
            description="day grain date bound reports the final included date",
            end="2015-01-01",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.DAY,
            expected_end="2014-12-31",
        ),
        InclusiveCursorEndTestCase(
            description="date bound without a grain still reports the final included date",
            end="2026-04-25",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=None,
            expected_end="2026-04-24",
        ),
        InclusiveCursorEndTestCase(
            description="timestamp bound without a grain steps back one second",
            end="2014-12-31T12:00:00",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=None,
            expected_end="2014-12-31T11:59:59",
        ),
        InclusiveCursorEndTestCase(
            description="hour grain timestamp bound steps back one hour",
            end="2014-12-31T12:00:00",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.HOUR,
            expected_end="2014-12-31T11:00:00",
        ),
        InclusiveCursorEndTestCase(
            description="month grain date bound reports the final included date",
            end="2015-01-01",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.MONTH,
            expected_end="2014-12-31",
        ),
        InclusiveCursorEndTestCase(
            description="integer bound reports the final included value",
            end="201",
            cursor_type=CursorType.INTEGER,
            cursor_grain=None,
            expected_end="200",
        ),
        InclusiveCursorEndTestCase(
            description="unparsable bound is reported unchanged",
            end="__SQB_CURSOR_END__",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=None,
            expected_end="__SQB_CURSOR_END__",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_exclusive_bound_when_formatting_then_reports_final_included_value(
    test_case: InclusiveCursorEndTestCase,
) -> None:
    result: str = inclusive_cursor_end(
        end=test_case.end,
        cursor_type=test_case.cursor_type,
        cursor_grain=test_case.cursor_grain,
    )

    assert result == test_case.expected_end
