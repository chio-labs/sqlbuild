"""PostgreSQL execution history integration fixtures."""

import uuid
from collections.abc import Iterable, Iterator
from threading import Event
from typing import Any
from unittest.mock import Mock

import pytest

from sqlbuild.execution_history import (
    CanonicalLifecycleEvent,
    ExecutionHistoryStorageError,
    RunRecord,
    StoredEvent,
)
from sqlbuild.postgres_history import PostgresExecutionHistory


@pytest.fixture(scope="module")
def postgres_container_dsn() -> Iterator[str]:
    from testcontainers.postgres import PostgresContainer

    container: PostgresContainer = PostgresContainer("postgres:17")
    try:
        container.start()
    except Exception as error:
        pytest.skip(f"Docker not available for PostgreSQL execution history: {error}")
    try:
        yield container.get_connection_url().replace("postgresql+psycopg2://", "postgresql://")
    finally:
        container.stop()


@pytest.fixture
def postgres_history_dsn(postgres_container_dsn: str) -> Iterator[str]:
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    schema: str = f"sqlbuild_history_{uuid.uuid4().hex}"
    with psycopg.connect(postgres_container_dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    yield make_conninfo(postgres_container_dsn, options=f"-c search_path={schema}")
    with psycopg.connect(postgres_container_dsn, autocommit=True) as connection:
        connection.execute(
            sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
        )


@pytest.fixture
def retry_once_postgres_history(postgres_history_dsn: str) -> Iterator[Any]:
    import psycopg

    class RetryOnceHistory(PostgresExecutionHistory):
        def __init__(self, dsn: str) -> None:
            self.attempts = 0
            self._failure = Mock(
                side_effect=(
                    psycopg.errors.SerializationFailure("injected serialization failure"),
                    None,
                )
            )
            super().__init__(dsn)

        def _append_events(
            self,
            *,
            cursor: Any,
            events: tuple[CanonicalLifecycleEvent, ...],
        ) -> tuple[StoredEvent, ...]:
            self.attempts += 1
            _ = self._failure()
            return super()._append_events(cursor=cursor, events=events)

    storage: RetryOnceHistory = RetryOnceHistory(postgres_history_dsn)
    yield storage
    storage.close()


@pytest.fixture
def application_failure_postgres_history(postgres_history_dsn: str) -> Iterator[Any]:
    class ApplicationFailureHistory(PostgresExecutionHistory):
        def __init__(self, dsn: str) -> None:
            self.attempts = 0
            self._failure = Mock(side_effect=RuntimeError("injected application failure"))
            super().__init__(dsn)

        def _append_events(
            self,
            *,
            cursor: Any,
            events: tuple[CanonicalLifecycleEvent, ...],
        ) -> tuple[StoredEvent, ...]:
            self.attempts += 1
            _ = self._failure()
            return super()._append_events(cursor=cursor, events=events)

    storage: ApplicationFailureHistory = ApplicationFailureHistory(postgres_history_dsn)
    yield storage
    storage.close()


@pytest.fixture
def paused_plain_append(postgres_history_dsn: str) -> Iterator[tuple[Any, ...]]:
    allocated: Event = Event()
    release: Event = Event()

    class PausedAppendHistory(PostgresExecutionHistory):
        def _append_events(
            self,
            *,
            cursor: Any,
            events: tuple[CanonicalLifecycleEvent, ...],
        ) -> tuple[StoredEvent, ...]:
            stored: tuple[StoredEvent, ...] = super()._append_events(cursor=cursor, events=events)
            allocated.set()
            _ = release.wait(timeout=10)
            return stored

    first: PausedAppendHistory = PausedAppendHistory(postgres_history_dsn)
    second: PostgresExecutionHistory = PostgresExecutionHistory(postgres_history_dsn)
    yield first, second, allocated, release
    release.set()
    first.close()
    second.close()


@pytest.fixture
def acknowledgement_loss_history(postgres_history_dsn: str) -> Iterator[PostgresExecutionHistory]:
    class AcknowledgementLossHistory(PostgresExecutionHistory):
        def append_and_project(
            self, events: Iterable[CanonicalLifecycleEvent]
        ) -> tuple[StoredEvent, ...]:
            _ = super().append_and_project(events)
            raise ExecutionHistoryStorageError(
                "PostgreSQL commit acknowledgement was lost; reconstruct storage and retry"
            )

    storage: AcknowledgementLossHistory = AcknowledgementLossHistory(postgres_history_dsn)
    yield storage
    storage.close()


@pytest.fixture
def projection_failure_history(postgres_history_dsn: str) -> Iterator[PostgresExecutionHistory]:
    class ProjectionFailureHistory(PostgresExecutionHistory):
        def __init__(self, dsn: str) -> None:
            self._fail_publication = False
            super().__init__(dsn)
            self._fail_publication = True

        def _replace_projection(self, *, cursor: Any, projected: tuple[RunRecord, ...]) -> None:
            if self._fail_publication:
                raise ExecutionHistoryStorageError("injected projection publication failure")
            super()._replace_projection(cursor=cursor, projected=projected)

    storage: ProjectionFailureHistory = ProjectionFailureHistory(postgres_history_dsn)
    yield storage
    storage.close()


@pytest.fixture
def paused_reconcile(postgres_history_dsn: str) -> Iterator[tuple[Any, ...]]:
    read_complete: Event = Event()
    release: Event = Event()

    class PausedReconcileHistory(PostgresExecutionHistory):
        def __init__(self, dsn: str) -> None:
            self._coordinate = False
            super().__init__(dsn)
            self._coordinate = True

        def _read_all_events(self, *, cursor: Any) -> tuple[StoredEvent, ...]:
            stored: tuple[StoredEvent, ...] = super()._read_all_events(cursor=cursor)
            if self._coordinate:
                read_complete.set()
                _ = release.wait(timeout=10)
            return stored

    reconciler: PausedReconcileHistory = PausedReconcileHistory(postgres_history_dsn)
    writer: PostgresExecutionHistory = PostgresExecutionHistory(postgres_history_dsn)
    yield reconciler, writer, read_complete, release
    release.set()
    reconciler.close()
    writer.close()
