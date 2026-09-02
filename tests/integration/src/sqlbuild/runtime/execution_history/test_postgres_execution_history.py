"""PostgreSQL migration, concurrency, conformance, and lifecycle integration tests."""

import json
import os
import subprocess
import sys
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError
from dataclasses import replace
from typing import Any

import pytest

from sqlbuild.execution_history import (
    CanonicalLifecycleEvent,
    EventFilter,
    EventPage,
    ExecutionHistoryStorageError,
    IntegrityConflictError,
    RunFilter,
    RunPage,
    StoredEvent,
    UnsupportedSchemaVersionError,
    canonical_event_content,
)
from sqlbuild.observability import LifecycleEvent, OpaqueLifecycleEvent, lifecycle_event_to_json
from sqlbuild.postgres_history import PostgresExecutionHistory
from tests.integration.src.sqlbuild.runtime.execution_history._test_types import (
    PostgresHistoryCase,
)
from tests.integration.src.sqlbuild.runtime.execution_history.helpers import lifecycle_event

pytestmark: list[object] = [pytest.mark.postgres, pytest.mark.real_warehouse]


@pytest.mark.parametrize(
    "test_case",
    (
        PostgresHistoryCase(
            description="first migration and reopen preserve durable history",
            expected_event_count=2,
            expected_run_count=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_empty_database_when_migrating_appending_and_reopening_then_history_is_healthy(
    postgres_history_dsn: str, test_case: PostgresHistoryCase
) -> None:
    first: PostgresExecutionHistory = PostgresExecutionHistory(postgres_history_dsn)
    _ = first.append_events((lifecycle_event("start"), lifecycle_event("end", "run_completed")))
    event_cursor: str | None = first.get_events(event_filter=EventFilter(), limit=1).next_cursor
    first.close()

    reopened: PostgresExecutionHistory = PostgresExecutionHistory(postgres_history_dsn)
    remaining: EventPage = reopened.get_events(
        event_filter=EventFilter(), after_cursor=event_cursor, limit=1
    )
    runs: RunPage = reopened.get_runs(run_filter=RunFilter())

    assert reopened.check_health() is True
    assert reopened.get_schema_version() == 1
    assert (
        len(reopened.get_events(event_filter=EventFilter()).records)
        == test_case.expected_event_count
    )
    assert len(remaining.records) == 1
    assert len(runs.records) == test_case.expected_run_count
    assert runs.records[0].is_complete is True
    reopened.dispose()
    reopened.dispose()
    with pytest.raises(ExecutionHistoryStorageError, match="closed"):
        reopened.get_events(event_filter=EventFilter())


@pytest.mark.parametrize(
    "test_case",
    (
        PostgresHistoryCase(
            description="concurrent identical publication stores exactly one fact",
            expected_event_count=1,
            expected_run_count=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_concurrent_instances_when_publishing_identical_event_then_fact_and_projection_converge(
    postgres_history_dsn: str, test_case: PostgresHistoryCase
) -> None:
    event: CanonicalLifecycleEvent = lifecycle_event("concurrent", run_id="concurrent-run")

    with ThreadPoolExecutor(max_workers=2) as executor:
        opened: tuple[PostgresExecutionHistory, ...] = tuple(
            executor.map(PostgresExecutionHistory, (postgres_history_dsn, postgres_history_dsn))
        )
        storages: tuple[PostgresExecutionHistory, PostgresExecutionHistory] = (
            opened[0],
            opened[1],
        )
        results: tuple[tuple[StoredEvent, ...], ...] = tuple(
            executor.map(lambda storage: storage.append_and_project((event,)), storages)
        )

    inspection: PostgresExecutionHistory = PostgresExecutionHistory(postgres_history_dsn)
    matching_events: EventPage = inspection.get_events(
        event_filter=EventFilter(run_id="concurrent-run")
    )
    matching_runs: RunPage = inspection.get_runs(run_filter=RunFilter(invocation_id="invocation-1"))

    assert results[0][0] == results[1][0]
    assert len(matching_events.records) == test_case.expected_event_count
    assert (
        sum(run.run_id == "concurrent-run" for run in matching_runs.records)
        == test_case.expected_run_count
    )
    for storage in storages:
        storage.close()
    inspection.close()


@pytest.mark.parametrize(
    "test_case",
    (
        PostgresHistoryCase(
            description="paused identity allocation serializes visible cursor order",
            expected_event_count=2,
            expected_run_count=0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_first_plain_append_allocated_but_uncommitted_when_second_appends_then_second_waits_without_cursor_hole(
    paused_plain_append: tuple[Any, ...], test_case: PostgresHistoryCase
) -> None:
    first, second, allocated, release = paused_plain_append
    known: LifecycleEvent = lifecycle_event("known-first", run_id="cursor-run")
    opaque: OpaqueLifecycleEvent = OpaqueLifecycleEvent(
        raw={"event_id": "opaque-second", "schema_version": 2, "nested": {"kind": "opaque"}}
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future: Future[StoredEvent] = executor.submit(first.append_event, known)
        assert allocated.wait(timeout=5) is True
        second_future: Future[StoredEvent] = executor.submit(second.append_event, opaque)
        with pytest.raises(TimeoutError):
            second_future.result(timeout=0.1)
        release.set()
        first_stored: StoredEvent = first_future.result(timeout=5)
        second_stored: StoredEvent = second_future.result(timeout=5)

    after_first: EventPage = second.get_events(
        event_filter=EventFilter(), after_cursor=first_stored.cursor
    )
    after_second: EventPage = second.get_events(
        event_filter=EventFilter(), after_cursor=second_stored.cursor
    )
    assert first_stored.storage_order < second_stored.storage_order
    assert after_first.records == (second_stored,)
    assert len(after_first.records) == test_case.expected_event_count - 1
    assert len(after_second.records) == test_case.expected_run_count


@pytest.mark.parametrize(
    "test_case",
    (
        PostgresHistoryCase(
            description="known and opaque equivalent concurrent append is one fact",
            expected_event_count=1,
            expected_run_count=0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_known_and_opaque_equivalent_event_when_plain_appending_concurrently_then_one_fact_exists(
    postgres_history_dsn: str, test_case: PostgresHistoryCase
) -> None:
    known: LifecycleEvent = lifecycle_event("known-opaque-equivalent", run_id="equivalent-run")
    opaque_raw: object = json.loads(lifecycle_event_to_json(known))
    assert isinstance(opaque_raw, dict)
    opaque: OpaqueLifecycleEvent = OpaqueLifecycleEvent(raw=opaque_raw)
    storages: tuple[PostgresExecutionHistory, PostgresExecutionHistory] = (
        PostgresExecutionHistory(postgres_history_dsn),
        PostgresExecutionHistory(postgres_history_dsn),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures: tuple[Future[StoredEvent], Future[StoredEvent]] = (
            executor.submit(storages[0].append_event, known),
            executor.submit(storages[1].append_event, opaque),
        )
        results: tuple[StoredEvent, StoredEvent] = (
            futures[0].result(timeout=5),
            futures[1].result(timeout=5),
        )

    page: EventPage = storages[0].get_events(event_filter=EventFilter(run_id="equivalent-run"))
    assert results[0] == results[1]
    assert len(page.records) == test_case.expected_event_count
    assert test_case.expected_run_count == 0
    storages[0].close()
    storages[1].close()


@pytest.mark.parametrize(
    "test_case",
    (
        PostgresHistoryCase(
            description="conflicting known opaque batch rolls back every fact",
            expected_event_count=0,
            expected_run_count=0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_known_and_conflicting_opaque_same_id_when_plain_appending_batch_then_batch_is_atomic(
    postgres_history_dsn: str, test_case: PostgresHistoryCase
) -> None:
    storage: PostgresExecutionHistory = PostgresExecutionHistory(postgres_history_dsn)
    known: LifecycleEvent = lifecycle_event("known-opaque-conflict", run_id="conflict-run")
    opaque: OpaqueLifecycleEvent = OpaqueLifecycleEvent(
        raw={
            **json.loads(lifecycle_event_to_json(known)),
            "producer": "conflicting-opaque-producer",
        }
    )

    with pytest.raises(IntegrityConflictError):
        storage.append_events((lifecycle_event("fresh-in-conflict"), known, opaque))

    page: EventPage = storage.get_events(event_filter=EventFilter())
    assert len(page.records) == test_case.expected_event_count
    assert test_case.expected_run_count == 0
    storage.close()


@pytest.mark.parametrize(
    "test_case",
    (
        PostgresHistoryCase(
            description="opaque nul and oversized number preserve canonical text",
            expected_event_count=1,
            expected_run_count=0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_opaque_nested_nul_and_jsonb_oversized_number_when_roundtripping_then_canonical_text_is_exact(
    postgres_history_dsn: str, test_case: PostgresHistoryCase
) -> None:
    previous_limit: int = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(0)
    huge_number: int = 10**140_000
    event: OpaqueLifecycleEvent = OpaqueLifecycleEvent(
        raw={
            "event_id": "opaque-text-only",
            "schema_version": 2,
            "nested": {"nul": "before\u0000after", "huge": huge_number},
        }
    )
    expected_content: str = canonical_event_content(event)
    storage: PostgresExecutionHistory = PostgresExecutionHistory(postgres_history_dsn)
    stored: StoredEvent = storage.append_event(event)
    page: EventPage = storage.get_events(event_filter=EventFilter())

    assert len(page.records) == test_case.expected_event_count
    assert canonical_event_content(stored.event) == expected_content
    assert canonical_event_content(page.records[0].event) == expected_content
    assert test_case.expected_run_count == 0
    storage.close()
    sys.set_int_max_str_digits(previous_limit)


@pytest.mark.parametrize(
    "test_case",
    (
        PostgresHistoryCase(
            description="conflicting batch rolls back fresh fact",
            expected_event_count=1,
            expected_run_count=0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_existing_id_when_mixed_batch_conflicts_then_whole_batch_rolls_back(
    postgres_history_dsn: str, test_case: PostgresHistoryCase
) -> None:
    storage: PostgresExecutionHistory = PostgresExecutionHistory(postgres_history_dsn)
    original: CanonicalLifecycleEvent = lifecycle_event("conflict-original", run_id="conflict-run")
    _ = storage.append_event(original)

    with pytest.raises(IntegrityConflictError):
        storage.append_events(
            (
                lifecycle_event("fresh-before-conflict", run_id="fresh-run"),
                replace(original, producer="conflicting-producer"),
            )
        )

    conflict_events: EventPage = storage.get_events(event_filter=EventFilter(run_id="conflict-run"))
    fresh_events: EventPage = storage.get_events(event_filter=EventFilter(run_id="fresh-run"))
    assert len(conflict_events.records) == test_case.expected_event_count
    assert len(fresh_events.records) == test_case.expected_run_count
    storage.close()


@pytest.mark.parametrize(
    "test_case",
    (
        PostgresHistoryCase(
            description="serialization retries but application failure does not",
            expected_event_count=2,
            expected_run_count=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_retryable_and_application_failures_when_appending_then_only_serialization_retries(
    retry_once_postgres_history: Any,
    application_failure_postgres_history: Any,
    test_case: PostgresHistoryCase,
) -> None:
    stored: StoredEvent = retry_once_postgres_history.append_event(lifecycle_event("retryable"))

    with pytest.raises(RuntimeError, match="application failure"):
        application_failure_postgres_history.append_event(lifecycle_event("application"))

    assert stored.event == lifecycle_event("retryable")
    assert retry_once_postgres_history.attempts == test_case.expected_event_count
    assert application_failure_postgres_history.attempts == test_case.expected_run_count


@pytest.mark.parametrize(
    "test_case",
    (
        PostgresHistoryCase(
            description="commit acknowledgement loss recovers by reconstructed retry",
            expected_event_count=1,
            expected_run_count=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_server_commit_without_ack_when_reconstructing_and_retrying_same_id_then_one_fact_exists(
    postgres_history_dsn: str,
    acknowledgement_loss_history: PostgresExecutionHistory,
    test_case: PostgresHistoryCase,
) -> None:
    event: LifecycleEvent = lifecycle_event("ambiguous-commit", run_id="ambiguous-run")

    with pytest.raises(ExecutionHistoryStorageError, match="acknowledgement") as captured:
        acknowledgement_loss_history.append_and_project((event,))
    acknowledgement_loss_history.close()

    reconstructed: PostgresExecutionHistory = PostgresExecutionHistory(postgres_history_dsn)
    retried: tuple[StoredEvent, ...] = reconstructed.append_and_project((event,))
    page: EventPage = reconstructed.get_events(event_filter=EventFilter(run_id="ambiguous-run"))
    run_page: RunPage = reconstructed.get_runs(run_filter=RunFilter())

    assert "password" not in str(captured.value).lower()
    assert retried == page.records
    assert len(page.records) == test_case.expected_event_count
    assert len(run_page.records) == test_case.expected_run_count
    assert run_page.records[0].last_storage_order == retried[0].storage_order
    reconstructed.close()


@pytest.mark.parametrize(
    "test_case",
    (
        PostgresHistoryCase(
            description="projection failure rolls back event and projection",
            expected_event_count=0,
            expected_run_count=0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_projection_publication_failure_after_insert_when_appending_atomically_then_nothing_commits(
    postgres_history_dsn: str,
    projection_failure_history: PostgresExecutionHistory,
    test_case: PostgresHistoryCase,
) -> None:
    with pytest.raises(ExecutionHistoryStorageError, match="projection publication failure"):
        projection_failure_history.append_and_project(
            (lifecycle_event("rolled-back-event", run_id="rolled-back-run"),)
        )

    inspection: PostgresExecutionHistory = PostgresExecutionHistory(postgres_history_dsn)
    page: EventPage = inspection.get_events(event_filter=EventFilter(run_id="rolled-back-run"))
    run_page: RunPage = inspection.get_runs(run_filter=RunFilter())
    assert len(page.records) == test_case.expected_event_count
    assert len(run_page.records) == test_case.expected_run_count
    inspection.close()


@pytest.mark.parametrize(
    "test_case",
    (
        PostgresHistoryCase(
            description="same run concurrent distinct events never regress projection cursor",
            expected_event_count=2,
            expected_run_count=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_same_run_distinct_events_when_appending_atomically_concurrently_then_projection_uses_latest_storage_order(
    postgres_history_dsn: str, test_case: PostgresHistoryCase
) -> None:
    storages: tuple[PostgresExecutionHistory, PostgresExecutionHistory] = (
        PostgresExecutionHistory(postgres_history_dsn),
        PostgresExecutionHistory(postgres_history_dsn),
    )
    events: tuple[LifecycleEvent, LifecycleEvent] = (
        lifecycle_event("same-run-start", run_id="same-concurrent-run"),
        lifecycle_event("same-run-terminal", "run_completed", run_id="same-concurrent-run"),
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures: tuple[Future[tuple[StoredEvent, ...]], Future[tuple[StoredEvent, ...]]] = (
            executor.submit(storages[0].append_and_project, (events[0],)),
            executor.submit(storages[1].append_and_project, (events[1],)),
        )
        stored: tuple[StoredEvent, StoredEvent] = (
            futures[0].result(timeout=5)[0],
            futures[1].result(timeout=5)[0],
        )

    run_page: RunPage = storages[0].get_runs(run_filter=RunFilter())
    page: EventPage = storages[0].get_events(event_filter=EventFilter(run_id="same-concurrent-run"))
    assert len(page.records) == test_case.expected_event_count
    assert len(run_page.records) == test_case.expected_run_count
    assert run_page.records[0].last_storage_order == max(event.storage_order for event in stored)
    storages[0].close()
    storages[1].close()


@pytest.mark.parametrize(
    "test_case",
    (
        PostgresHistoryCase(
            description="reconcile and append project share one lock order",
            expected_event_count=2,
            expected_run_count=2,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_reconcile_has_history_lock_when_append_and_project_starts_then_writer_waits_and_both_converge(
    paused_reconcile: tuple[Any, ...], test_case: PostgresHistoryCase
) -> None:
    reconciler, writer, read_complete, release = paused_reconcile
    _ = writer.append_and_project((lifecycle_event("seed", run_id="seed-run"),))

    with ThreadPoolExecutor(max_workers=2) as executor:
        reconcile_future: Future[tuple[Any, ...]] = executor.submit(reconciler.reconcile)
        assert read_complete.wait(timeout=5) is True
        writer_future: Future[tuple[StoredEvent, ...]] = executor.submit(
            writer.append_and_project,
            (lifecycle_event("after-reconcile", run_id="writer-run"),),
        )
        with pytest.raises(TimeoutError):
            writer_future.result(timeout=0.1)
        release.set()
        _ = reconcile_future.result(timeout=5)
        _ = writer_future.result(timeout=5)

    page: EventPage = writer.get_events(event_filter=EventFilter())
    runs: RunPage = writer.get_runs(run_filter=RunFilter())
    assert len(page.records) == test_case.expected_event_count
    assert len(runs.records) == test_case.expected_run_count


@pytest.mark.parametrize(
    "test_case",
    (
        PostgresHistoryCase(
            description="newer revision rejects without destructive reset",
            expected_event_count=2,
            expected_run_count=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_newer_schema_when_opening_then_revision_is_rejected_and_preserved(
    postgres_history_dsn: str, test_case: PostgresHistoryCase
) -> None:
    import psycopg

    initialized: PostgresExecutionHistory = PostgresExecutionHistory(postgres_history_dsn)
    initialized.close()

    with psycopg.connect(postgres_history_dsn, autocommit=True) as connection:
        connection.execute(
            "UPDATE sqlbuild_storage_migrations SET schema_version = %s",
            (test_case.expected_event_count,),
        )

    with pytest.raises(UnsupportedSchemaVersionError, match=str(test_case.expected_event_count)):
        PostgresExecutionHistory(postgres_history_dsn)

    with psycopg.connect(postgres_history_dsn, autocommit=True) as connection:
        row: tuple[int] | None = connection.execute(
            "SELECT schema_version FROM sqlbuild_storage_migrations"
        ).fetchone()
        assert row is not None
        revision: int = row[0]
        connection.execute(
            "UPDATE sqlbuild_storage_migrations SET schema_version = %s",
            (test_case.expected_run_count,),
        )
    assert revision == test_case.expected_event_count


@pytest.mark.parametrize(
    "test_case",
    (
        PostgresHistoryCase(
            description="config and connection errors redact explicit secret",
            expected_event_count=0,
            expected_run_count=0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_secret_dsn_when_connection_fails_then_error_and_repr_are_redacted(
    test_case: PostgresHistoryCase,
) -> None:
    secret: str = "super-secret-password"
    dsn: str = f"postgresql://sqlbuild:{secret}@127.0.0.1:1/missing"

    with pytest.raises(ExecutionHistoryStorageError) as captured:
        PostgresExecutionHistory(dsn, connect_timeout_seconds=1)

    assert secret not in str(captured.value)
    assert secret not in repr(captured.value)
    assert test_case.expected_event_count == test_case.expected_run_count


@pytest.mark.parametrize(
    "test_case",
    (
        PostgresHistoryCase(
            description="shared conformance suite runs against DSN gated backend",
            expected_event_count=0,
            expected_run_count=0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_postgres_dsn_when_running_shared_conformance_then_exact_contract_passes(
    postgres_history_dsn: str, test_case: PostgresHistoryCase
) -> None:
    environment: dict[str, str] = dict(os.environ)
    environment["SQLBUILD_TEST_POSTGRES_DSN"] = postgres_history_dsn
    result: subprocess.CompletedProcess[str] = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/src/sqlbuild/runtime/execution_history/conformance",
            "-vv",
            "-k",
            "PostgreSQL",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == test_case.expected_event_count, result.stdout + result.stderr
    assert "deployed PostgreSQL backend" in result.stdout
    assert " passed" in result.stdout
    assert test_case.expected_run_count == 0
