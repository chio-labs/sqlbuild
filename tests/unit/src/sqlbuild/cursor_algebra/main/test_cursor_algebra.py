"""Exhaustive invariant tests for typed cursor interval algebra."""

from datetime import date, datetime

import pytest

from sqlbuild.compiler.planner.types import CursorGrain, CursorType
from sqlbuild.cursor_algebra.main.cap_from_end import cap_from_end
from sqlbuild.cursor_algebra.main.cap_from_start import cap_from_start
from sqlbuild.cursor_algebra.main.clamp import clamp
from sqlbuild.cursor_algebra.main.compare import compare
from sqlbuild.cursor_algebra.main.exclusive_end_from_observed_max import (
    exclusive_end_from_observed_max,
)
from sqlbuild.cursor_algebra.main.exclusive_to_inclusive import exclusive_to_inclusive
from sqlbuild.cursor_algebra.main.floor_to_grain import floor_to_grain
from sqlbuild.cursor_algebra.main.inclusive_to_exclusive import inclusive_to_exclusive
from sqlbuild.cursor_algebra.main.max_bound import max_bound
from sqlbuild.cursor_algebra.main.merge import merge
from sqlbuild.cursor_algebra.main.min_bound import min_bound
from sqlbuild.cursor_algebra.main.next_boundary import next_boundary
from sqlbuild.cursor_algebra.main.observed_partition import observed_partition
from sqlbuild.cursor_algebra.main.parse import parse
from sqlbuild.cursor_algebra.main.render import render
from sqlbuild.cursor_algebra.main.sentinel_from_token import sentinel_from_token
from sqlbuild.cursor_algebra.main.sentinel_to_token import sentinel_to_token
from sqlbuild.cursor_algebra.main.split_into_batches import split_into_batches
from sqlbuild.cursor_algebra.models import AlignedInterval, IntegerValue
from sqlbuild.cursor_algebra.types import BoundSentinel, CursorScalar
from tests.unit.src.sqlbuild.cursor_algebra.main._test_types import (
    CursorAlgebraMatrixCase,
    IntegerOrderingCase,
    IntervalOperationsTestCase,
    TemporalSplitTestCase,
)
from tests.unit.src.sqlbuild.cursor_algebra.main.helpers import build_temporal_values

POSITIONS: tuple[datetime, ...] = (
    datetime(2024, 1, 1),
    datetime(2024, 7, 15, 12, 30, 45, 123456),
    datetime(2024, 12, 31, 23, 59, 59, 999999),
)


TEMPORAL_VALUES: tuple[object, ...] = build_temporal_values(positions=POSITIONS)


@pytest.mark.parametrize(
    "test_case",
    [
        CursorAlgebraMatrixCase(
            description="second_matrix",
            grain=CursorGrain.SECOND,
            raw_values=TEMPORAL_VALUES,
            expected_value_count=9,
        ),
        CursorAlgebraMatrixCase(
            description="minute_matrix",
            grain=CursorGrain.MINUTE,
            raw_values=TEMPORAL_VALUES,
            expected_value_count=9,
        ),
        CursorAlgebraMatrixCase(
            description="hour_matrix",
            grain=CursorGrain.HOUR,
            raw_values=TEMPORAL_VALUES,
            expected_value_count=9,
        ),
        CursorAlgebraMatrixCase(
            description="day_matrix",
            grain=CursorGrain.DAY,
            raw_values=TEMPORAL_VALUES,
            expected_value_count=9,
        ),
        CursorAlgebraMatrixCase(
            description="month_matrix",
            grain=CursorGrain.MONTH,
            raw_values=TEMPORAL_VALUES,
            expected_value_count=9,
        ),
        CursorAlgebraMatrixCase(
            description="year_matrix",
            grain=CursorGrain.YEAR,
            raw_values=TEMPORAL_VALUES,
            expected_value_count=9,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_temporal_matrix_when_applying_algebra_then_invariants_hold(
    test_case: CursorAlgebraMatrixCase,
) -> None:
    assert len(test_case.raw_values) == test_case.expected_value_count
    for raw in test_case.raw_values:
        scalar: CursorScalar = parse(raw=raw, cursor_type=CursorType.TIMESTAMP)
        floored: CursorScalar = floor_to_grain(value=scalar, grain=test_case.grain)
        refloored: CursorScalar = floor_to_grain(value=floored, grain=test_case.grain)
        boundary: CursorScalar = next_boundary(value=floored, grain=test_case.grain)
        interval: AlignedInterval = observed_partition(value=scalar, grain=test_case.grain)
        rendered: str = render(value=scalar)
        reparsed: CursorScalar = parse(raw=rendered, cursor_type=CursorType.TIMESTAMP)
        source_was_date: bool = isinstance(raw, date) and not isinstance(raw, datetime)

        assert refloored == floored
        assert compare(left=floored, right=boundary) < 0
        assert compare(left=interval.start, right=interval.end) < 0
        assert floor_to_grain(value=interval.start, grain=test_case.grain) == interval.start
        assert floor_to_grain(value=interval.end, grain=test_case.grain) == interval.end
        assert render(value=reparsed) == rendered
        assert ("T" not in rendered) == source_was_date


@pytest.mark.parametrize(
    "test_case",
    [
        IntegerOrderingCase(
            description="single_digit_before_two_digits",
            values=("9", "10"),
            expected_minimum="9",
            expected_maximum="10",
        ),
        IntegerOrderingCase(
            description="two_digits_before_three_digits",
            values=("100", "99"),
            expected_minimum="99",
            expected_maximum="100",
        ),
        IntegerOrderingCase(
            description="decimal_integral_spelling",
            values=("25.0", "9"),
            expected_minimum="9",
            expected_maximum="25.0",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_integer_strings_when_selecting_bounds_then_uses_numeric_order(
    test_case: IntegerOrderingCase,
) -> None:
    assert min_bound(values=test_case.values, cursor_type=CursorType.INTEGER) == (
        test_case.expected_minimum
    )
    assert max_bound(values=test_case.values, cursor_type=CursorType.INTEGER) == (
        test_case.expected_maximum
    )
    for raw in test_case.values:
        scalar: CursorScalar = parse(raw=raw, cursor_type=CursorType.INTEGER)
        assert isinstance(scalar, IntegerValue)
        for grain in CursorGrain:
            assert floor_to_grain(value=scalar, grain=grain) == scalar
            assert compare(left=scalar, right=next_boundary(value=scalar, grain=grain)) < 0


@pytest.mark.parametrize(
    "test_case",
    [
        IntervalOperationsTestCase(
            description="six_values_in_two_value_batches",
            start=0,
            end=6,
            step=2,
            expected_batch_count=3,
            expected_final_end=6,
        ),
        IntervalOperationsTestCase(
            description="large_integer_range_uses_arithmetic_steps",
            start=0,
            end=200_000_000,
            step=10_000_000,
            expected_batch_count=20,
            expected_final_end=200_000_000,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_typed_interval_when_composing_operations_then_boundaries_remain_canonical(
    test_case: IntervalOperationsTestCase,
) -> None:
    interval: AlignedInterval = AlignedInterval(
        start=IntegerValue(value=test_case.start),
        end=IntegerValue(value=test_case.end),
        grain=None,
    )
    bounds: AlignedInterval = AlignedInterval(
        start=IntegerValue(value=test_case.start + test_case.step),
        end=IntegerValue(value=test_case.end),
        grain=None,
    )
    batches: tuple[AlignedInterval, ...] = split_into_batches(
        interval=interval, step=test_case.step
    )

    assert len(batches) == test_case.expected_batch_count
    assert batches[-1].end == IntegerValue(value=test_case.expected_final_end)
    assert clamp(interval=interval, bounds=bounds) == bounds
    assert merge(intervals=batches) == (interval,)
    assert cap_from_start(intervals=batches, count=1) == batches[:1]
    assert cap_from_end(intervals=batches, count=1) == batches[-1:]
    assert exclusive_end_from_observed_max(value=IntegerValue(value=5), grain=None) == (
        IntegerValue(value=6)
    )
    assert exclusive_to_inclusive(
        value=inclusive_to_exclusive(value=IntegerValue(value=5), grain=None), grain=None
    ) == IntegerValue(value=5)
    assert sentinel_from_token(token=sentinel_to_token(sentinel=BoundSentinel.START)) == (
        BoundSentinel.START
    )


@pytest.mark.parametrize(
    "test_case",
    [
        TemporalSplitTestCase(
            description="two_month_calendar_batches",
            grain=CursorGrain.MONTH,
            start="2025-01-01T00:00:00",
            end="2025-06-01T00:00:00",
            step=2,
            expected_boundaries=(
                "2025-01-01T00:00:00",
                "2025-03-01T00:00:00",
                "2025-05-01T00:00:00",
                "2025-06-01T00:00:00",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_temporal_interval_when_splitting_then_advances_once_per_batch(
    test_case: TemporalSplitTestCase,
) -> None:
    start: CursorScalar = parse(raw=test_case.start, cursor_type=CursorType.TIMESTAMP)
    end: CursorScalar = parse(raw=test_case.end, cursor_type=CursorType.TIMESTAMP)
    interval: AlignedInterval = AlignedInterval(start=start, end=end, grain=test_case.grain)
    batches: tuple[AlignedInterval, ...] = split_into_batches(
        interval=interval, step=test_case.step
    )
    boundaries: tuple[str, ...] = (
        render(value=batches[0].start),
        *(render(value=batch.end) for batch in batches),
    )

    assert boundaries == test_case.expected_boundaries


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
