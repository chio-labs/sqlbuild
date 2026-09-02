"""Execution history append and projection failure-window contract tests."""

from collections.abc import Callable

import pytest

from sqlbuild.execution_history import (
    EventFilter,
    EventLogStorage,
    EventPage,
    ExecutionHistoryStorageError,
    RunRecord,
    RunStorage,
    StoredEvent,
    append_and_project,
)
from tests.unit.src.sqlbuild.runtime.execution_history.conformance._test_types import ContractCase
from tests.unit.src.sqlbuild.runtime.execution_history.conformance.helpers import lifecycle_event


@pytest.mark.parametrize(
    "test_case",
    [
        ContractCase(
            description="durable append survives projection failure and replay repairs",
            expected_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_append_commits_and_projection_fails_when_rebuilding_then_durable_log_repairs_projection(
    event_log_factory: Callable[[], EventLogStorage],
    project_failing_run_storage: RunStorage,
    run_storage_factory: Callable[[], RunStorage],
    test_case: ContractCase,
) -> None:
    event_log: EventLogStorage = event_log_factory()

    with pytest.raises(ExecutionHistoryStorageError, match="injected projection failure"):
        append_and_project(
            event_log=event_log,
            run_storage=project_failing_run_storage,
            events=(lifecycle_event("started"),),
        )

    durable: EventPage = event_log.get_events(event_filter=EventFilter(), limit=100)
    repaired: RunStorage = run_storage_factory()
    rebuilt: tuple[RunRecord, ...] = repaired.rebuild_from_events(durable.records)
    assert len(durable.records) == test_case.expected_count
    assert len(rebuilt) == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="append failure prevents projection publication", expected_count=0)],
    ids=lambda case: case.description,
)
def test_given_append_fails_when_coordinating_then_projection_is_not_called(
    append_failing_event_log: EventLogStorage,
    tracking_run_storage: tuple[RunStorage, Callable[[], int]],
    test_case: ContractCase,
) -> None:
    run_storage, project_call_count = tracking_run_storage

    with pytest.raises(ExecutionHistoryStorageError, match="injected append failure"):
        append_and_project(
            event_log=append_failing_event_log,
            run_storage=run_storage,
            events=(lifecycle_event("started"),),
        )

    assert run_storage.get_run("run-1") is None
    assert project_call_count() == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    [
        ContractCase(
            description="post-computation failure publishes no partial projection and rebuild repairs",
            expected_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_projection_publication_fails_after_compute_when_rebuilding_same_store_then_no_partial_state_leaks(
    event_log: EventLogStorage,
    atomic_failing_run_storage: RunStorage,
    test_case: ContractCase,
) -> None:
    initial: tuple[StoredEvent, ...] = event_log.append_events(
        (lifecycle_event("run-1-start", run_id="run-1"),)
    )
    _ = atomic_failing_run_storage.rebuild_from_events(initial)
    durable_update: tuple[StoredEvent, ...] = event_log.append_events(
        (
            lifecycle_event("run-1-end", "run_completed", run_id="run-1"),
            lifecycle_event("run-2-start", run_id="run-2"),
        )
    )

    with pytest.raises(ExecutionHistoryStorageError, match="atomic projection publication failure"):
        atomic_failing_run_storage.project(durable_update)

    unchanged: RunRecord | None = atomic_failing_run_storage.get_run("run-1")
    assert unchanged is not None
    assert unchanged.is_complete is False
    assert atomic_failing_run_storage.get_run("run-2") is None

    durable: EventPage = event_log.get_events(event_filter=EventFilter())
    repaired: tuple[RunRecord, ...] = atomic_failing_run_storage.rebuild_from_events(
        durable.records
    )
    assert len(repaired) == test_case.expected_count
    completed: RunRecord | None = atomic_failing_run_storage.get_run("run-1")
    assert completed is not None
    assert completed.is_complete is True
    assert atomic_failing_run_storage.get_run("run-2") is not None
