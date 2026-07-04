"""Tests for cursor_start lower-floor behavior."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.helpers.resolve.cursor import compute_cursor_bounds
from sqlbuild.compiler.planner.models import CursorBounds, ModelCursorSnapshot
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    CursorStartBoundsTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CursorStartBoundsTestCase(
            description="first run clamps upstream minimum to configured floor",
            target_max=None,
            upstream_mins=("2024-01-01T00:00:00",),
            upstream_maxes=("2024-02-01T00:00:00",),
            cursor_type="timestamp",
            cursor_start="2024-01-15T00:00:00",
            lookback=None,
            backfill_duration=None,
            start_cursor_override=None,
            end_cursor_override=None,
            expected_start="2024-01-15T00:00:00",
            expected_end="2024-02-01T00:00:00",
        ),
        CursorStartBoundsTestCase(
            description="lookback cannot move before configured floor",
            target_max="2024-02-10T00:00:00",
            upstream_mins=("2024-01-01T00:00:00",),
            upstream_maxes=("2024-02-20T00:00:00",),
            cursor_type="timestamp",
            cursor_start="2024-02-05T00:00:00",
            lookback="10d",
            backfill_duration=None,
            start_cursor_override=None,
            end_cursor_override=None,
            expected_start="2024-02-05T00:00:00",
            expected_end="2024-02-20T00:00:00",
        ),
        CursorStartBoundsTestCase(
            description="bounded backfill cannot move before configured floor",
            target_max="2024-02-10T00:00:00",
            upstream_mins=("2024-01-01T00:00:00",),
            upstream_maxes=("2024-02-20T00:00:00",),
            cursor_type="timestamp",
            cursor_start="2024-02-01T00:00:00",
            lookback=None,
            backfill_duration="30d",
            start_cursor_override=None,
            end_cursor_override=None,
            expected_start="2024-02-01T00:00:00",
            expected_end="2024-02-20T00:00:00",
        ),
        CursorStartBoundsTestCase(
            description="cli start below configured floor is clamped",
            target_max="2024-02-10T00:00:00",
            upstream_mins=("2024-01-01T00:00:00",),
            upstream_maxes=("2024-02-20T00:00:00",),
            cursor_type="timestamp",
            cursor_start="2024-02-05T00:00:00",
            lookback=None,
            backfill_duration=None,
            start_cursor_override="2024-02-01T00:00:00",
            end_cursor_override=None,
            expected_start="2024-02-05T00:00:00",
            expected_end="2024-02-20T00:00:00",
        ),
        CursorStartBoundsTestCase(
            description="cli start above configured floor wins naturally",
            target_max="2024-02-10T00:00:00",
            upstream_mins=("2024-01-01T00:00:00",),
            upstream_maxes=("2024-02-20T00:00:00",),
            cursor_type="timestamp",
            cursor_start="2024-02-05T00:00:00",
            lookback=None,
            backfill_duration=None,
            start_cursor_override="2024-02-12T00:00:00",
            end_cursor_override=None,
            expected_start="2024-02-12T00:00:00",
            expected_end="2024-02-20T00:00:00",
        ),
        CursorStartBoundsTestCase(
            description="integer cursor start clamps lower bound",
            target_max=None,
            upstream_mins=("50",),
            upstream_maxes=("200",),
            cursor_type="integer",
            cursor_start="100",
            lookback=None,
            backfill_duration=None,
            start_cursor_override=None,
            end_cursor_override=None,
            expected_start="100",
            expected_end="200",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cursor_start_when_computing_bounds_then_applies_lower_floor(
    test_case: CursorStartBoundsTestCase,
) -> None:
    cursor_bounds: CursorBounds | None = compute_cursor_bounds(
        cursor_snapshot=ModelCursorSnapshot(
            target_max=test_case.target_max,
            upstream_mins=test_case.upstream_mins,
            upstream_maxes=test_case.upstream_maxes,
        ),
        cursor_type=test_case.cursor_type,
        cursor_start=test_case.cursor_start,
        lookback=test_case.lookback,
        backfill_duration=test_case.backfill_duration,
        start_cursor_override=test_case.start_cursor_override,
        end_cursor_override=test_case.end_cursor_override,
        is_microbatch=False,
    )

    assert cursor_bounds is not None
    assert cursor_bounds.start == test_case.expected_start
    assert cursor_bounds.end == test_case.expected_end
