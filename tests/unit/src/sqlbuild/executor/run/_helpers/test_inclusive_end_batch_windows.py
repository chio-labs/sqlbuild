"""End-to-end characterization: an operator-supplied inclusive end must be
advanced so the half-open batch windows include the final cursor value.

This is the regression net for the bug where ``--end-cursor-ts 2014-12-31``
built windows over ``[start, 2014-12-31)`` and silently dropped the final day.
"""

from __future__ import annotations

import pytest

from sqlbuild.compiler.planner._helpers.output.inclusive_cursor_end import advance_cursor_end
from sqlbuild.compiler.planner.types import CursorGrain, CursorType
from sqlbuild.executor.run._helpers.materializations.microbatch import compute_batch_windows
from sqlbuild.executor.run.models import BatchWindow
from tests.unit.src.sqlbuild.executor.run._helpers._test_types import (
    InclusiveEndBatchWindowTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        InclusiveEndBatchWindowTestCase(
            description="full year of monthly batches includes the final day",
            start="2014-01-01T00:00:00",
            inclusive_end="2014-12-31",
            batch_size="1mo",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.DAY,
            expected_batch_count=12,
            expected_final_window_end="2015-01-01T00:00:00",
            expected_final_value_included=True,
        ),
        InclusiveEndBatchWindowTestCase(
            description="daily batches include the final hour boundary",
            start="2026-01-01T00:00:00",
            inclusive_end="2026-01-03T00:00:00",
            batch_size="1d",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.DAY,
            expected_batch_count=3,
            expected_final_window_end="2026-01-04T00:00:00",
            expected_final_value_included=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_inclusive_end_when_building_batch_windows_then_final_value_is_included(
    test_case: InclusiveEndBatchWindowTestCase,
) -> None:
    exclusive_end: str = advance_cursor_end(
        value=test_case.inclusive_end,
        cursor_type=test_case.cursor_type,
        cursor_grain=test_case.cursor_grain,
    )

    windows: tuple[BatchWindow, ...] = compute_batch_windows(
        start=test_case.start,
        end=exclusive_end,
        batch_size=test_case.batch_size,
        cursor_type=test_case.cursor_type,
    )

    final_window: BatchWindow = windows[-1]
    final_value_included: bool = test_case.inclusive_end < final_window.end

    assert len(windows) == test_case.expected_batch_count
    assert final_window.end == test_case.expected_final_window_end
    assert final_value_included == test_case.expected_final_value_included
