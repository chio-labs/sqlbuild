"""Bounded inspection reads keep input order and fail deterministically."""

from __future__ import annotations

import threading
import time

import pytest

from sqlbuild.adapter.relations.main.run_bounded_inspections import run_bounded_inspections
from tests.unit.src.sqlbuild.adapter.relations.main.run_bounded_inspections._test_types import (
    BoundedInspectionFailureTestCase,
    BoundedInspectionTestCase,
    InFlightFailureTestCase,
    InterruptedInspectionTestCase,
)
from tests.unit.src.sqlbuild.adapter.relations.main.run_bounded_inspections.helpers import (
    ConcurrencyTracker,
    StartRecordingTasks,
    failing_outcomes,
    interrupt_on_first_completion,
    interrupting_outcomes,
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


@pytest.mark.parametrize(
    "test_case",
    [
        InterruptedInspectionTestCase(
            description="interrupt raised by read 0 stops queued reads",
            task_count=40,
            concurrency=8,
            task_seconds=0.2,
            interrupt_in_task=True,
            expected_max_seconds=0.6,
            expected_max_started=9,
        ),
        InterruptedInspectionTestCase(
            description="interrupt raised while reporting read 0 returns without waiting",
            task_count=40,
            concurrency=8,
            task_seconds=0.2,
            interrupt_in_task=False,
            expected_max_seconds=0.6,
            expected_max_started=16,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_keyboard_interrupt_when_reads_are_queued_then_raises_promptly_without_new_reads(
    test_case: InterruptedInspectionTestCase,
) -> None:
    latencies: tuple[float, ...] = (0.0,) * test_case.interrupt_in_task + (
        test_case.task_seconds,
    ) * (test_case.task_count - test_case.interrupt_in_task)
    recorder: StartRecordingTasks = StartRecordingTasks(
        latencies=latencies,
        outcomes=interrupting_outcomes(interrupt_in_task=test_case.interrupt_in_task),
    )
    started_at: float = time.monotonic()

    with pytest.raises(KeyboardInterrupt):
        _ = run_bounded_inspections(
            tasks=recorder.tasks(),
            concurrency=test_case.concurrency,
            on_complete=interrupt_on_first_completion(interrupt=not test_case.interrupt_in_task),
        )

    elapsed: float = time.monotonic() - started_at
    started_when_raised: int = len(recorder.started)
    time.sleep(test_case.task_seconds * 2)
    assert elapsed < test_case.expected_max_seconds
    assert len(recorder.started) == started_when_raised
    assert len(recorder.started) <= test_case.expected_max_started


@pytest.mark.parametrize(
    "test_case",
    [
        InFlightFailureTestCase(
            description="slow lower-index failure wins over an earlier higher-index failure",
            task_seconds=(0.0, 0.15, 0.0, 0.0, 0.0, 0.3, 0.3, 0.3),
            failing_indexes=frozenset({1, 4}),
            concurrency=8,
            expected_error="read 1 failed",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_failures_from_running_reads_when_collecting_then_reports_lowest_index(
    test_case: InFlightFailureTestCase,
) -> None:
    recorder: StartRecordingTasks = StartRecordingTasks(
        latencies=test_case.task_seconds,
        outcomes=failing_outcomes(test_case.failing_indexes),
    )

    with pytest.raises(RuntimeError, match=test_case.expected_error):
        _ = run_bounded_inspections(tasks=recorder.tasks(), concurrency=test_case.concurrency)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
