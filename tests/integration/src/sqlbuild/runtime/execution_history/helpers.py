"""Canonical event builders for SQLite integration tests."""

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from threading import Event

from sqlbuild.execution_history import RunRecord, StoredEvent
from sqlbuild.observability import LifecycleEvent
from sqlbuild.sqlite_history import SQLiteExecutionHistory


class _CoordinatedReconcileHistory(SQLiteExecutionHistory):
    def __init__(self, *, path: Path, read_started: Event, release_reconcile: Event) -> None:
        self._read_started = Event()
        self._release_reconcile = Event()
        self._release_reconcile.set()
        super().__init__(path=path)
        self._read_started = read_started
        self._release_reconcile = release_reconcile

    def _read_all_events(self) -> tuple[StoredEvent, ...]:
        records: tuple[StoredEvent, ...] = super()._read_all_events()
        self._read_started.set()
        _ = self._release_reconcile.wait(timeout=5)
        return records


def lifecycle_event(
    event_id: str,
    event_type: str = "run_started",
    *,
    invocation_id: str = "invocation-1",
    run_id: str = "run-1",
    occurred_at: datetime = datetime(2026, 1, 1, tzinfo=UTC),
) -> LifecycleEvent:
    """Build one valid run-correlated lifecycle event."""

    return LifecycleEvent(
        event_id=event_id,
        event_type=event_type,
        schema_version=1,
        producer="sqlbuild",
        producer_version="test",
        occurred_at=occurred_at,
        invocation_id=invocation_id,
        run_id=run_id,
        payload={},
    )


def reconcile_with_coordination(
    *, path: Path, read_started: Event, release_reconcile: Event
) -> tuple[RunRecord, ...]:
    """Reconcile while exposing the post-read transaction point to a test."""

    storage: SQLiteExecutionHistory = _CoordinatedReconcileHistory(
        path=path,
        read_started=read_started,
        release_reconcile=release_reconcile,
    )
    result: tuple[RunRecord, ...] = storage.reconcile()
    storage.close()
    return result


def append_atomically(*, path: Path, events: Iterable[LifecycleEvent]) -> tuple[StoredEvent, ...]:
    """Append and project from an independently owned SQLite connection."""

    storage: SQLiteExecutionHistory = SQLiteExecutionHistory(path=path)
    result: tuple[StoredEvent, ...] = storage.append_and_project(events)
    storage.close()
    return result
