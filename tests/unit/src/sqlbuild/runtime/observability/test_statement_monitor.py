"""Tests for statement monitoring cost and deferred monitor threads."""

import pytest

from tests.unit.src.sqlbuild.runtime.observability._test_types import (
    DeferredMonitorCase,
    DeferredStartCancellationCase,
    FailedMonitorStartCase,
    FastStatementMonitorCase,
    FinishedStatementRetentionCase,
)
from tests.unit.src.sqlbuild.runtime.observability.helpers import (
    count_monitor_thread_starts,
    heartbeats_after_early_stop,
    heartbeats_past_threshold,
    live_lifecycles_after_large_statements,
    run_cancelled_deferred_start,
    statement_events_when_monitor_start_fails,
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


@pytest.mark.parametrize(
    "test_case",
    [
        FinishedStatementRetentionCase(
            description="finished statements with large SQL are not retained",
            statement_count=200,
            sql_bytes=100_000,
            expected_live_lifecycles=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_finished_statements_when_collecting_then_no_lifecycle_is_retained(
    test_case: FinishedStatementRetentionCase,
) -> None:
    live: int = live_lifecycles_after_large_statements(
        statement_count=test_case.statement_count, sql_bytes=test_case.sql_bytes
    )

    assert live == test_case.expected_live_lifecycles


@pytest.mark.parametrize(
    "test_case",
    [
        DeferredStartCancellationCase(
            description="cancelled start is forgotten and never runs",
            delay_seconds=0.02,
            expected_pending=0,
            expected_runs=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cancelled_deferred_start_when_deadline_passes_then_it_never_runs(
    test_case: DeferredStartCancellationCase,
) -> None:
    pending, runs = run_cancelled_deferred_start(delay_seconds=test_case.delay_seconds)

    assert pending == test_case.expected_pending
    assert runs == test_case.expected_runs


@pytest.mark.parametrize(
    "test_case",
    [
        DeferredMonitorCase(
            description="statement outliving a lowered threshold still heartbeats",
            threshold_seconds=0.02,
            query_id="",
            expected_submissions=("heartbeat",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_statement_past_threshold_when_deferred_start_runs_then_it_heartbeats(
    test_case: DeferredMonitorCase,
) -> None:
    heartbeats: int = heartbeats_past_threshold(threshold_seconds=test_case.threshold_seconds)

    assert heartbeats >= len(test_case.expected_submissions)


@pytest.mark.parametrize(
    "test_case",
    [
        FailedMonitorStartCase(
            description="refused monitor thread still completes the statement once",
            threshold_seconds=0.01,
            expected_event_types=("statement_started", "statement_completed"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_monitor_thread_cannot_start_when_statement_finishes_then_it_completes(
    test_case: FailedMonitorStartCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    event_types: tuple[str, ...] = statement_events_when_monitor_start_fails(
        monkeypatch=monkeypatch, threshold_seconds=test_case.threshold_seconds
    )

    assert event_types == test_case.expected_event_types


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
