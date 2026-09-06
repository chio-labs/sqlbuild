"""Reusable run projection storage conformance harness."""

from collections.abc import Callable
from datetime import timedelta

import pytest

from sqlbuild.execution_history import (
    EventFilter,
    EventPage,
    InvalidCursorError,
    LifecycleEventLogStorage,
    RunFilter,
    RunPage,
    RunRecord,
    RunStatus,
    RunStorage,
    StoredEvent,
)
from tests.unit.src.sqlbuild.runtime.execution_history.conformance._test_types import (
    ContractCase,
    ProjectionCase,
)
from tests.unit.src.sqlbuild.runtime.execution_history.conformance.helpers import (
    BASE_TIME,
    lifecycle_event,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ProjectionCase(
            description="start-only run remains unknown and incomplete",
            expected_status="unknown",
            expected_complete=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_started_run_without_terminal_when_projecting_then_status_remains_unknown(
    event_log: LifecycleEventLogStorage, run_storage: RunStorage, test_case: ProjectionCase
) -> None:
    stored: tuple[StoredEvent, ...] = event_log.append_events((lifecycle_event("started"),))

    projected: tuple[RunRecord, ...] = run_storage.project(stored)

    assert projected[0].status.value == test_case.expected_status
    assert projected[0].is_complete is test_case.expected_complete
    assert projected[0].ended_at is None


@pytest.mark.parametrize(
    "test_case",
    [
        ProjectionCase(
            description="later storage-order terminal wins despite earlier occurred-at",
            expected_status="failed",
            expected_complete=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_out_of_order_timestamps_and_conflicting_terminals_when_projecting_then_storage_order_wins(
    event_log: LifecycleEventLogStorage, run_storage: RunStorage, test_case: ProjectionCase
) -> None:
    stored: tuple[StoredEvent, ...] = event_log.append_events(
        (
            lifecycle_event("started", occurred_at=BASE_TIME + timedelta(hours=3)),
            lifecycle_event(
                "completed", "run_completed", occurred_at=BASE_TIME + timedelta(hours=2)
            ),
            lifecycle_event("failed", "run_failed", occurred_at=BASE_TIME + timedelta(hours=1)),
        )
    )

    projected: tuple[RunRecord, ...] = run_storage.project(reversed(stored))

    assert projected[0].status.value == test_case.expected_status
    assert projected[0].is_complete is test_case.expected_complete
    assert projected[0].started_at == BASE_TIME + timedelta(hours=3)
    assert projected[0].ended_at == BASE_TIME + timedelta(hours=1)


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="incremental and rebuild records are identical", expected_count=2)],
    ids=lambda case: case.description,
)
def test_given_durable_run_facts_when_projecting_incrementally_and_rebuilding_then_results_match(
    event_log: LifecycleEventLogStorage,
    run_storage_factory: Callable[[], RunStorage],
    test_case: ContractCase,
) -> None:
    stored: tuple[StoredEvent, ...] = event_log.append_events(
        (
            lifecycle_event("run-1-start", run_id="run-1"),
            lifecycle_event("run-2-start", run_id="run-2"),
            lifecycle_event("run-1-end", "run_completed", run_id="run-1"),
        )
    )
    incremental: RunStorage = run_storage_factory()
    rebuilt: RunStorage = run_storage_factory()

    _ = incremental.project(stored[:2])
    incremental_records: tuple[RunRecord, ...] = incremental.project(stored[1:])
    rebuilt_records: tuple[RunRecord, ...] = rebuilt.rebuild_from_events(stored)

    assert incremental_records == rebuilt_records
    assert len(rebuilt_records) == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="run pages use exclusive opaque cursors", expected_count=3)],
    ids=lambda case: case.description,
)
def test_given_multiple_runs_when_paging_then_compound_order_has_no_gaps_or_duplicates(
    event_log: LifecycleEventLogStorage, run_storage: RunStorage, test_case: ContractCase
) -> None:
    stored: tuple[StoredEvent, ...] = event_log.append_events(
        tuple(lifecycle_event(f"event-{index}", run_id=f"run-{index}") for index in range(3))
    )
    _ = run_storage.project(stored)
    first: RunPage = run_storage.get_runs(run_filter=RunFilter(), limit=2)
    second: RunPage = run_storage.get_runs(
        run_filter=RunFilter(), after_cursor=first.next_cursor, limit=2
    )
    run_ids: tuple[str, ...] = tuple(run.run_id for run in first.records + second.records)

    assert run_ids == ("run-0", "run-1", "run-2")
    assert len(set(run_ids)) == test_case.expected_count
    assert first.has_more is True
    assert second.has_more is False


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="status and invocation filters compose", expected_count=1)],
    ids=lambda case: case.description,
)
def test_given_projected_runs_when_filtering_then_only_matching_runs_are_returned(
    event_log: LifecycleEventLogStorage, run_storage: RunStorage, test_case: ContractCase
) -> None:
    stored: tuple[StoredEvent, ...] = event_log.append_events(
        (
            lifecycle_event("run-1", run_id="run-1", invocation_id="invocation-1"),
            lifecycle_event("run-2", run_id="run-2", invocation_id="invocation-2"),
            lifecycle_event(
                "run-2-end",
                "run_completed",
                run_id="run-2",
                invocation_id="invocation-2",
            ),
        )
    )
    _ = run_storage.project(stored)

    page: RunPage = run_storage.get_runs(
        run_filter=RunFilter(invocation_id="invocation-2", statuses=(RunStatus.COMPLETED,)),
        limit=100,
    )

    assert len(page.records) == test_case.expected_count
    assert page.records[0].run_id == "run-2"


@pytest.mark.parametrize(
    "test_case",
    [
        ContractCase(
            description="run filter time boundaries are inclusive and composable", expected_count=1
        )
    ],
    ids=lambda case: case.description,
)
def test_given_projected_runs_when_composing_identity_status_and_created_range_then_boundaries_are_inclusive(
    event_log: LifecycleEventLogStorage, run_storage: RunStorage, test_case: ContractCase
) -> None:
    stored: tuple[StoredEvent, ...] = event_log.append_events(
        (
            lifecycle_event("run-1", run_id="run-1", invocation_id="selected"),
            lifecycle_event("run-1-end", "run_completed", run_id="run-1", invocation_id="selected"),
            lifecycle_event("run-2", run_id="run-2", invocation_id="other"),
        )
    )
    projected: tuple[RunRecord, ...] = run_storage.project(stored)
    selected: RunRecord = projected[0]

    page: RunPage = run_storage.get_runs(
        run_filter=RunFilter(
            invocation_id="selected",
            statuses=(RunStatus.COMPLETED,),
            created_at_start=selected.created_at,
            created_at_end=selected.created_at,
        )
    )

    assert len(page.records) == test_case.expected_count
    assert page.records[0].run_id == "run-1"


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="missing run and empty query return no records", expected_count=0)],
    ids=lambda case: case.description,
)
def test_given_empty_projection_when_reading_then_missing_run_and_page_are_empty(
    run_storage: RunStorage, test_case: ContractCase
) -> None:
    page: RunPage = run_storage.get_runs(run_filter=RunFilter(), limit=100)

    assert run_storage.get_run("absent") is None
    assert len(page.records) == test_case.expected_count
    assert page.next_cursor is None
    assert page.has_more is False


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="reapplying durable positions is ignored", expected_count=1)],
    ids=lambda case: case.description,
)
def test_given_already_applied_positions_when_projecting_again_then_projection_does_not_advance(
    event_log: LifecycleEventLogStorage, run_storage: RunStorage, test_case: ContractCase
) -> None:
    stored: tuple[StoredEvent, ...] = event_log.append_events((lifecycle_event("started"),))
    first: tuple[RunRecord, ...] = run_storage.project(stored)

    second: tuple[RunRecord, ...] = run_storage.project(stored)

    assert second == first
    assert second[0].last_storage_order == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="duplicate supplied durable position is ignored", expected_count=1)],
    ids=lambda case: case.description,
)
def test_given_duplicate_durable_position_in_batch_when_projecting_then_fact_is_applied_once(
    event_log: LifecycleEventLogStorage, run_storage: RunStorage, test_case: ContractCase
) -> None:
    stored: tuple[StoredEvent, ...] = event_log.append_events((lifecycle_event("started"),))

    projected: tuple[RunRecord, ...] = run_storage.project(stored + stored)

    assert len(projected) == test_case.expected_count
    assert projected[0].last_storage_order == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="event log can replay all durable facts", expected_count=1)],
    ids=lambda case: case.description,
)
def test_given_backend_factories_when_rebuilding_then_harness_remains_backend_neutral(
    event_log_factory: Callable[[], LifecycleEventLogStorage],
    run_storage_factory: Callable[[], RunStorage],
    test_case: ContractCase,
) -> None:
    event_log: LifecycleEventLogStorage = event_log_factory()
    run_storage: RunStorage = run_storage_factory()
    _ = event_log.append_event(lifecycle_event("started"))
    page: EventPage = event_log.get_events(event_filter=EventFilter(), limit=100)

    rebuilt: tuple[RunRecord, ...] = run_storage.rebuild_from_events(page.records)

    assert len(rebuilt) == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="run cursor remains valid across filter changes", expected_count=1)],
    ids=lambda case: case.description,
)
def test_given_global_run_cursor_for_filtered_out_run_when_changing_filter_then_next_match_is_returned(
    event_log: LifecycleEventLogStorage, run_storage: RunStorage, test_case: ContractCase
) -> None:
    stored: tuple[StoredEvent, ...] = event_log.append_events(
        (
            lifecycle_event("first", run_id="run-1", invocation_id="other"),
            lifecycle_event("second", run_id="run-2", invocation_id="selected"),
        )
    )
    _ = run_storage.project(stored)
    first: RunPage = run_storage.get_runs(run_filter=RunFilter(), limit=1)

    filtered: RunPage = run_storage.get_runs(
        run_filter=RunFilter(invocation_id="selected"),
        after_cursor=first.next_cursor,
        limit=1,
    )

    assert len(filtered.records) == test_case.expected_count
    assert filtered.records[0].run_id == "run-2"


@pytest.mark.parametrize(
    "test_case",
    [
        ContractCase(
            description="filtered run pagination has no gaps or duplicates", expected_count=2
        )
    ],
    ids=lambda case: case.description,
)
def test_given_interleaved_runs_when_paging_filtered_results_then_global_cursor_is_exclusive_without_gaps(
    event_log: LifecycleEventLogStorage, run_storage: RunStorage, test_case: ContractCase
) -> None:
    stored: tuple[StoredEvent, ...] = event_log.append_events(
        (
            lifecycle_event("run-1", run_id="run-1", invocation_id="selected"),
            lifecycle_event("run-2", run_id="run-2", invocation_id="other"),
            lifecycle_event("run-3", run_id="run-3", invocation_id="selected"),
        )
    )
    _ = run_storage.project(stored)
    run_filter: RunFilter = RunFilter(invocation_id="selected")
    first: RunPage = run_storage.get_runs(run_filter=run_filter, limit=1)
    second: RunPage = run_storage.get_runs(
        run_filter=run_filter, after_cursor=first.next_cursor, limit=1
    )
    run_ids: tuple[str, ...] = tuple(run.run_id for run in first.records + second.records)

    assert run_ids == ("run-1", "run-3")
    assert len(set(run_ids)) == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="equal created times use run ID tie ordering", expected_count=2)],
    ids=lambda case: case.description,
)
def test_given_runs_with_equal_created_time_when_paging_then_run_id_breaks_ordering_tie(
    run_storage: RunStorage, test_case: ContractCase
) -> None:
    stored: tuple[StoredEvent, ...] = (
        StoredEvent(
            storage_order=1,
            cursor="event:1",
            received_at=BASE_TIME,
            event=lifecycle_event("b", run_id="run-b"),
        ),
        StoredEvent(
            storage_order=2,
            cursor="event:2",
            received_at=BASE_TIME,
            event=lifecycle_event("a", run_id="run-a"),
        ),
    )
    _ = run_storage.project(stored)

    page: RunPage = run_storage.get_runs(run_filter=RunFilter(), limit=10)

    assert tuple(run.run_id for run in page.records) == ("run-a", "run-b")
    assert len(page.records) == test_case.expected_count


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="foreign run cursor is rejected", expected_count=0)],
    ids=lambda case: case.description,
)
def test_given_invalid_or_foreign_run_cursor_when_reading_then_cursor_error_is_raised(
    event_log: LifecycleEventLogStorage,
    run_storage: RunStorage,
    run_storage_factory: Callable[[], RunStorage],
    test_case: ContractCase,
) -> None:
    stored: tuple[StoredEvent, ...] = event_log.append_events(
        (lifecycle_event("local", run_id="local-run"),)
    )
    _ = run_storage.project(stored)
    foreign: RunStorage = run_storage_factory()
    foreign_stored: tuple[StoredEvent, ...] = (
        StoredEvent(
            storage_order=1,
            cursor="foreign-event",
            received_at=BASE_TIME,
            event=lifecycle_event("foreign", run_id="foreign-run"),
        ),
    )
    _ = foreign.project(foreign_stored)
    foreign_page: RunPage = foreign.get_runs(run_filter=RunFilter(), limit=1)

    with pytest.raises(InvalidCursorError):
        run_storage.get_runs(
            run_filter=RunFilter(),
            after_cursor=foreign_page.next_cursor,
        )

    assert test_case.expected_count == 0


@pytest.mark.parametrize(
    "test_case",
    [ContractCase(description="malformed run cursor is rejected", expected_count=0)],
    ids=lambda case: case.description,
)
def test_given_malformed_run_cursor_when_reading_then_cursor_error_is_raised(
    run_storage: RunStorage, test_case: ContractCase
) -> None:
    with pytest.raises(InvalidCursorError):
        run_storage.get_runs(
            run_filter=RunFilter(), after_cursor=f"invalid:{test_case.description}"
        )

    assert test_case.expected_count == 0
