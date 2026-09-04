"""Tests for cursor bounds computation."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from sqlbuild.compiler.planner._helpers.output.inclusive_cursor_end import (
    discovered_cursor_partition,
)
from sqlbuild.compiler.planner._helpers.resolve.cursor import compute_cursor_bounds
from sqlbuild.compiler.planner.constants import (
    MICROBATCH_END_SENTINEL,
    MICROBATCH_START_SENTINEL,
)
from sqlbuild.compiler.planner.models import CursorBounds, ModelCursorSnapshot
from sqlbuild.compiler.planner.types import CursorGrain, CursorType
from tests.unit.src.sqlbuild.compiler.planner._helpers.resolve._test_types import (
    CursorBoundsTestCase,
    DiscoveredCursorPartitionTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DiscoveredCursorPartitionTestCase(
            "month boundary date", date(2026, 7, 1), "month", date(2026, 7, 1), date(2026, 8, 1)
        ),
        DiscoveredCursorPartitionTestCase(
            "month middle date", date(2026, 7, 15), "month", date(2026, 7, 1), date(2026, 8, 1)
        ),
        DiscoveredCursorPartitionTestCase(
            "month final date", date(2026, 7, 31), "month", date(2026, 7, 1), date(2026, 8, 1)
        ),
        DiscoveredCursorPartitionTestCase(
            "month middle timestamp string",
            "2026-07-15T12:30:45",
            "month",
            "2026-07-01T00:00:00",
            "2026-08-01T00:00:00",
        ),
        DiscoveredCursorPartitionTestCase(
            "month final timezone timestamp",
            datetime(2026, 7, 31, 23, 59, 59, tzinfo=timezone(timedelta(hours=5, minutes=30))),
            "month",
            datetime(2026, 7, 1, tzinfo=timezone(timedelta(hours=5, minutes=30))),
            datetime(2026, 8, 1, tzinfo=timezone(timedelta(hours=5, minutes=30))),
        ),
        DiscoveredCursorPartitionTestCase(
            "year boundary date", date(2026, 1, 1), "year", date(2026, 1, 1), date(2027, 1, 1)
        ),
        DiscoveredCursorPartitionTestCase(
            "year middle date", date(2026, 7, 15), "year", date(2026, 1, 1), date(2027, 1, 1)
        ),
        DiscoveredCursorPartitionTestCase(
            "year final timestamp",
            datetime(2026, 12, 31, 23, 59, 59),
            "year",
            datetime(2026, 1, 1),
            datetime(2027, 1, 1),
        ),
        DiscoveredCursorPartitionTestCase(
            "day middle timestamp",
            datetime(2026, 7, 15, 12, 30),
            "day",
            datetime(2026, 7, 15),
            datetime(2026, 7, 16),
        ),
        DiscoveredCursorPartitionTestCase(
            "day plain date", "2026-07-15", "day", "2026-07-15", "2026-07-16"
        ),
        DiscoveredCursorPartitionTestCase(
            "plain date without grain",
            "2026-07-15",
            None,
            "2026-07-15",
            "2026-07-16",
        ),
        DiscoveredCursorPartitionTestCase(
            "naive timestamp without grain",
            "2026-07-15T12:30:45",
            None,
            "2026-07-15T12:30:45",
            "2026-07-15T12:30:46",
        ),
        DiscoveredCursorPartitionTestCase(
            "hour middle timestamp",
            datetime(2026, 7, 15, 12, 30, 59),
            "hour",
            datetime(2026, 7, 15, 12),
            datetime(2026, 7, 15, 13),
        ),
        DiscoveredCursorPartitionTestCase(
            "hour plain date",
            "2026-07-15",
            "hour",
            "2026-07-15T00:00:00",
            "2026-07-15T01:00:00",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_observed_timestamp_when_resolving_partition_then_boundaries_are_grain_aligned(
    test_case: DiscoveredCursorPartitionTestCase,
) -> None:
    assert discovered_cursor_partition(
        value=test_case.value,
        cursor_type=CursorType.TIMESTAMP,
        cursor_grain=test_case.cursor_grain,
    ) == (test_case.expected_start, test_case.expected_end)


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
            description="typed timestamp advances the upstream maximum to an exclusive end",
            cursor_snapshot=ModelCursorSnapshot(
                target_max="2024-01-10T00:00:00",
                upstream_mins=("2024-01-01T00:00:00",),
                upstream_maxes=("2024-01-15T06:00:00",),
            ),
            lookback=None,
            backfill_duration=None,
            start_cursor_override=None,
            end_cursor_override=None,
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.HOUR,
            is_microbatch=False,
            expected_bounds=CursorBounds(
                start="2024-01-10T00:00:00",
                end="2024-01-15T07:00:00",
            ),
        ),
        CursorBoundsTestCase(
            description="typed integer advances the upstream maximum to an exclusive end",
            cursor_snapshot=ModelCursorSnapshot(
                target_max="100",
                upstream_mins=("1",),
                upstream_maxes=("200",),
            ),
            lookback=None,
            backfill_duration=None,
            start_cursor_override=None,
            end_cursor_override=None,
            cursor_type=CursorType.INTEGER,
            is_microbatch=False,
            expected_bounds=CursorBounds(start="100", end="201"),
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
            description="operator end override advances the inclusive end to an exclusive bound",
            cursor_snapshot=ModelCursorSnapshot(
                target_max="2024-01-15",
                upstream_mins=("2024-01-01",),
                upstream_maxes=("2024-02-01",),
            ),
            lookback=None,
            backfill_duration=None,
            start_cursor_override=None,
            end_cursor_override="2024-01-20",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.DAY,
            is_microbatch=False,
            expected_bounds=CursorBounds(start="2024-01-15", end="2024-01-21"),
        ),
        CursorBoundsTestCase(
            description="lookback in months subtracts a calendar month from the start",
            cursor_snapshot=ModelCursorSnapshot(
                target_max="2024-03-15T00:00:00",
                upstream_mins=("2024-01-01T00:00:00",),
                upstream_maxes=("2024-04-01T00:00:00",),
            ),
            lookback="1mo",
            backfill_duration=None,
            start_cursor_override=None,
            end_cursor_override=None,
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.MONTH,
            is_microbatch=False,
            expected_bounds=CursorBounds(
                start="2024-02-15T00:00:00",
                end="2024-05-01T00:00:00",
            ),
        ),
        CursorBoundsTestCase(
            description="bounded backfill in months overrides start to end minus calendar months",
            cursor_snapshot=ModelCursorSnapshot(
                target_max="2024-03-01T00:00:00",
                upstream_mins=("2023-01-01T00:00:00",),
                upstream_maxes=("2024-04-01T00:00:00",),
            ),
            lookback=None,
            backfill_duration="2mo",
            start_cursor_override=None,
            end_cursor_override=None,
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.MONTH,
            is_microbatch=False,
            expected_bounds=CursorBounds(
                start="2024-03-01T00:00:00",
                end="2024-05-01T00:00:00",
            ),
        ),
        CursorBoundsTestCase(
            description="integer end override advances by one unit",
            cursor_snapshot=ModelCursorSnapshot(
                target_max="1000",
                upstream_mins=("1",),
                upstream_maxes=("2000",),
            ),
            lookback=None,
            backfill_duration=None,
            start_cursor_override=None,
            end_cursor_override="1500",
            cursor_type=CursorType.INTEGER,
            is_microbatch=False,
            expected_bounds=CursorBounds(start="1000", end="1501"),
        ),
        CursorBoundsTestCase(
            description="timestamp end override with a time component advances by grain",
            cursor_snapshot=ModelCursorSnapshot(
                target_max="2024-01-15T00:00:00",
                upstream_mins=("2024-01-01T00:00:00",),
                upstream_maxes=("2024-02-01T00:00:00",),
            ),
            lookback=None,
            backfill_duration=None,
            start_cursor_override=None,
            end_cursor_override="2024-01-20T06:00:00",
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=CursorGrain.HOUR,
            is_microbatch=False,
            expected_bounds=CursorBounds(start="2024-01-15T00:00:00", end="2024-01-20T07:00:00"),
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
        cursor_grain=test_case.cursor_grain,
        is_microbatch=test_case.is_microbatch,
    )

    assert result == test_case.expected_bounds
