"""Tests for cursor bounds computation."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.planner._helpers.resolve.cursor import compute_cursor_bounds
from sqlbuild.compiler.planner.constants import (
    MICROBATCH_END_SENTINEL,
    MICROBATCH_START_SENTINEL,
)
from sqlbuild.compiler.planner.models import CursorBounds, ModelCursorSnapshot
from tests.unit.src.sqlbuild.compiler.planner._helpers.resolve._test_types import (
    CursorBoundsTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CursorBoundsTestCase(
            description="normal incremental uses target max as start and min of upstream maxes as end",
            cursor_snapshot=ModelCursorSnapshot(
                target_max="2024-01-15",
                upstream_mins=("2024-01-01",),
                upstream_maxes=("2024-02-01",),
            ),
            lookback=None,
            backfill_duration=None,
            start_cursor_override=None,
            end_cursor_override=None,
            is_microbatch=False,
            expected_bounds=CursorBounds(start="2024-01-15", end="2024-02-01"),
        ),
        CursorBoundsTestCase(
            description="first run uses min of upstream mins as start",
            cursor_snapshot=ModelCursorSnapshot(
                target_max=None,
                upstream_mins=("2024-01-01", "2024-01-05"),
                upstream_maxes=("2024-02-01", "2024-01-20"),
            ),
            lookback=None,
            backfill_duration=None,
            start_cursor_override=None,
            end_cursor_override=None,
            is_microbatch=False,
            expected_bounds=CursorBounds(start="2024-01-01", end="2024-01-20"),
        ),
        CursorBoundsTestCase(
            description="end bound is minimum of upstream maxes across multiple inputs",
            cursor_snapshot=ModelCursorSnapshot(
                target_max="2024-01-10",
                upstream_mins=("2024-01-01",),
                upstream_maxes=("2024-02-01", "2024-01-15"),
            ),
            lookback=None,
            backfill_duration=None,
            start_cursor_override=None,
            end_cursor_override=None,
            is_microbatch=False,
            expected_bounds=CursorBounds(start="2024-01-10", end="2024-01-15"),
        ),
        CursorBoundsTestCase(
            description="lookback subtracts from start value",
            cursor_snapshot=ModelCursorSnapshot(
                target_max="2024-01-15T00:00:00",
                upstream_mins=("2024-01-01T00:00:00",),
                upstream_maxes=("2024-02-01T00:00:00",),
            ),
            lookback="1d",
            backfill_duration=None,
            start_cursor_override=None,
            end_cursor_override=None,
            is_microbatch=False,
            expected_bounds=CursorBounds(
                start="2024-01-14T00:00:00",
                end="2024-02-01T00:00:00",
            ),
        ),
        CursorBoundsTestCase(
            description="bounded backfill overrides start to end minus duration",
            cursor_snapshot=ModelCursorSnapshot(
                target_max="2024-01-01T00:00:00",
                upstream_mins=("2023-01-01T00:00:00",),
                upstream_maxes=("2024-02-01T00:00:00",),
            ),
            lookback=None,
            backfill_duration="30d",
            start_cursor_override=None,
            end_cursor_override=None,
            is_microbatch=False,
            expected_bounds=CursorBounds(
                start="2024-01-02T00:00:00",
                end="2024-02-01T00:00:00",
            ),
        ),
        CursorBoundsTestCase(
            description="operator start override replaces computed start",
            cursor_snapshot=ModelCursorSnapshot(
                target_max="2024-01-15",
                upstream_mins=("2024-01-01",),
                upstream_maxes=("2024-02-01",),
            ),
            lookback=None,
            backfill_duration=None,
            start_cursor_override="2024-01-10",
            end_cursor_override=None,
            is_microbatch=False,
            expected_bounds=CursorBounds(start="2024-01-10", end="2024-02-01"),
        ),
        CursorBoundsTestCase(
            description="operator end override replaces computed end",
            cursor_snapshot=ModelCursorSnapshot(
                target_max="2024-01-15",
                upstream_mins=("2024-01-01",),
                upstream_maxes=("2024-02-01",),
            ),
            lookback=None,
            backfill_duration=None,
            start_cursor_override=None,
            end_cursor_override="2024-01-20",
            is_microbatch=False,
            expected_bounds=CursorBounds(start="2024-01-15", end="2024-01-20"),
        ),
        CursorBoundsTestCase(
            description="microbatch returns sentinel values regardless of snapshot",
            cursor_snapshot=ModelCursorSnapshot(
                target_max="2024-01-15",
                upstream_mins=("2024-01-01",),
                upstream_maxes=("2024-02-01",),
            ),
            lookback=None,
            backfill_duration=None,
            start_cursor_override=None,
            end_cursor_override=None,
            is_microbatch=True,
            expected_bounds=CursorBounds(
                start=MICROBATCH_START_SENTINEL,
                end=MICROBATCH_END_SENTINEL,
            ),
        ),
        CursorBoundsTestCase(
            description="returns none when no upstream maxes exist",
            cursor_snapshot=ModelCursorSnapshot(
                target_max=None,
                upstream_mins=(),
                upstream_maxes=(),
            ),
            lookback=None,
            backfill_duration=None,
            start_cursor_override=None,
            end_cursor_override=None,
            is_microbatch=False,
            expected_bounds=None,
        ),
        CursorBoundsTestCase(
            description="integer cursor with lookback subtracts seconds",
            cursor_snapshot=ModelCursorSnapshot(
                target_max="1000",
                upstream_mins=("1",),
                upstream_maxes=("2000",),
            ),
            lookback="1h",
            backfill_duration=None,
            start_cursor_override=None,
            end_cursor_override=None,
            is_microbatch=False,
            expected_bounds=CursorBounds(start=str(1000 - 3600), end="2000"),
        ),
        CursorBoundsTestCase(
            description="backfill duration takes precedence over lookback",
            cursor_snapshot=ModelCursorSnapshot(
                target_max="2024-01-15T00:00:00",
                upstream_mins=("2024-01-01T00:00:00",),
                upstream_maxes=("2024-02-01T00:00:00",),
            ),
            lookback="1d",
            backfill_duration="7d",
            start_cursor_override=None,
            end_cursor_override=None,
            is_microbatch=False,
            expected_bounds=CursorBounds(
                start="2024-01-25T00:00:00",
                end="2024-02-01T00:00:00",
            ),
        ),
        CursorBoundsTestCase(
            description="start override prevents lookback from applying",
            cursor_snapshot=ModelCursorSnapshot(
                target_max="2024-01-15T00:00:00",
                upstream_mins=("2024-01-01T00:00:00",),
                upstream_maxes=("2024-02-01T00:00:00",),
            ),
            lookback="1d",
            backfill_duration=None,
            start_cursor_override="2024-01-12T00:00:00",
            end_cursor_override=None,
            is_microbatch=False,
            expected_bounds=CursorBounds(
                start="2024-01-12T00:00:00",
                end="2024-02-01T00:00:00",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_snapshot_and_config_when_computing_cursor_bounds_then_returns_expected(
    test_case: CursorBoundsTestCase,
) -> None:
    result: CursorBounds | None = compute_cursor_bounds(
        cursor_snapshot=test_case.cursor_snapshot,
        cursor_type=test_case.cursor_type,
        cursor_start=test_case.cursor_start,
        lookback=test_case.lookback,
        backfill_duration=test_case.backfill_duration,
        start_cursor_override=test_case.start_cursor_override,
        end_cursor_override=test_case.end_cursor_override,
        is_microbatch=test_case.is_microbatch,
    )

    assert result == test_case.expected_bounds
