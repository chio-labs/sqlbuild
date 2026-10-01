"""Tests for statement monitoring cost and deferred monitor threads."""

import pytest

from tests.unit.src.sqlbuild.runtime.observability._test_types import (
    DeferredMonitorCase,
    FastStatementMonitorCase,
)
from tests.unit.src.sqlbuild.runtime.observability.helpers import (
    count_monitor_thread_starts,
    heartbeats_after_early_stop,
    submissions_after_late_provider,
)


@pytest.mark.parametrize(
    "test_case",
    [
        FastStatementMonitorCase(
            description="fast statements without query IDs start no monitor thread",
            statement_count=200,
            expected_monitor_threads=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_fast_statements_without_query_ids_when_executing_then_no_monitor_thread_starts(
    test_case: FastStatementMonitorCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: int = count_monitor_thread_starts(
        monkeypatch=monkeypatch, statement_count=test_case.statement_count
    )

    assert started == test_case.expected_monitor_threads


@pytest.mark.parametrize(
    "test_case",
    [
        DeferredMonitorCase(
            description="provider installed after a deferred start is polled at once",
            threshold_seconds=30.0,
            query_id="01-query-orders",
            expected_submissions=("01-query-orders",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_deferred_monitor_when_provider_arrives_then_query_id_is_submitted_once(
    test_case: DeferredMonitorCase,
) -> None:
    submissions: tuple[str, ...] = submissions_after_late_provider(
        threshold_seconds=test_case.threshold_seconds, query_id=test_case.query_id
    )

    assert submissions == test_case.expected_submissions


@pytest.mark.parametrize(
    "test_case",
    [
        DeferredMonitorCase(
            description="monitor stopped before its threshold never heartbeats",
            threshold_seconds=0.02,
            query_id="",
            expected_submissions=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_monitor_stopped_before_threshold_when_deadline_passes_then_no_heartbeat(
    test_case: DeferredMonitorCase,
) -> None:
    heartbeats: int = heartbeats_after_early_stop(threshold_seconds=test_case.threshold_seconds)

    assert heartbeats == len(test_case.expected_submissions)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
