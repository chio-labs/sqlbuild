"""Bounded inspection reads keep input order and fail deterministically."""

from __future__ import annotations

import threading

import pytest

from sqlbuild.adapter.relations.main.run_bounded_inspections import run_bounded_inspections
from tests.unit.src.sqlbuild.adapter.relations.main.run_bounded_inspections._test_types import (
    BoundedInspectionFailureTestCase,
    BoundedInspectionTestCase,
)
from tests.unit.src.sqlbuild.adapter.relations.main.run_bounded_inspections.helpers import (
    ConcurrencyTracker,
)


@pytest.mark.parametrize(
    "test_case",
    [
        BoundedInspectionTestCase(
            description="sequential",
            task_count=5,
            concurrency=1,
            expected_results=(0, 10, 20, 30, 40),
            expected_parallel=False,
        ),
        BoundedInspectionTestCase(
            description="bounded parallel",
            task_count=20,
            concurrency=4,
            expected_results=tuple(index * 10 for index in range(20)),
            expected_parallel=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_independent_reads_when_running_then_returns_results_in_input_order(
    test_case: BoundedInspectionTestCase,
) -> None:
    tracker: ConcurrencyTracker = ConcurrencyTracker()
    completions: list[tuple[int, int, int]] = []

    results: list[int] = run_bounded_inspections(
        tasks=tracker.tasks(count=test_case.task_count, failing=frozenset()),
        concurrency=test_case.concurrency,
        on_complete=lambda index, result: completions.append(
            (index, result, threading.get_ident())
        ),
    )

    assert tuple(results) == test_case.expected_results
    assert tracker.max_active <= test_case.concurrency
    assert (tracker.max_active > 1) is test_case.expected_parallel
    assert sorted(index for index, _, _ in completions) == list(range(test_case.task_count))
    assert {thread for _, _, thread in completions} == {threading.get_ident()}


@pytest.mark.parametrize(
    "test_case",
    [
        BoundedInspectionFailureTestCase(
            description="lowest failing index wins regardless of finish order",
            task_count=12,
            concurrency=6,
            failing_indexes=frozenset({3, 4}),
            expected_error="read 3 failed",
        ),
        BoundedInspectionFailureTestCase(
            description="sequential failure stops at the failing read",
            task_count=6,
            concurrency=1,
            failing_indexes=frozenset({2}),
            expected_error="read 2 failed",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failing_read_when_running_then_raises_lowest_index_failure(
    test_case: BoundedInspectionFailureTestCase,
) -> None:
    tracker: ConcurrencyTracker = ConcurrencyTracker()

    with pytest.raises(RuntimeError, match=test_case.expected_error):
        _ = run_bounded_inspections(
            tasks=tracker.tasks(count=test_case.task_count, failing=test_case.failing_indexes),
            concurrency=test_case.concurrency,
        )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
