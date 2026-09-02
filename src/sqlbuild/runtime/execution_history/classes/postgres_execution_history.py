"""Deployed PostgreSQL execution history storage."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Any, Self
from uuid import uuid4

from sqlbuild.runtime.execution_history.constants import (
    CURRENT_RUN_STORAGE_SCHEMA_VERSION,
    DEFAULT_PAGE_LIMIT,
)
from sqlbuild.runtime.execution_history.exceptions import (
    ExecutionHistoryStorageError,
    IntegrityConflictError,
    InvalidCursorError,
    UnsupportedSchemaVersionError,
)
from sqlbuild.runtime.execution_history.main.canonical_event_content import canonical_event_content
from sqlbuild.runtime.execution_history.main.canonical_event_id import canonical_event_id
from sqlbuild.runtime.execution_history.main.project_runs import project_runs
from sqlbuild.runtime.execution_history.main.validate_page_limit import validate_page_limit
from sqlbuild.runtime.execution_history.models import (
    EventFilter,
    EventPage,
    RunFilter,
    RunPage,
    RunRecord,
    StoredEvent,
)
from sqlbuild.runtime.execution_history.types import CanonicalLifecycleEvent, RunStatus
from sqlbuild.runtime.observability.main.lifecycle_event_from_json import lifecycle_event_from_json
from sqlbuild.runtime.observability.models import LifecycleEvent, OpaqueLifecycleEvent

_CONNECT_TIMEOUT_SECONDS: int = 10
_STATEMENT_TIMEOUT_MS: int = 30_000
_MAX_TRANSACTION_RETRIES: int = 3
_MAX_CONNECT_TIMEOUT_SECONDS: int = 300
_MAX_STATEMENT_TIMEOUT_MS: int = 3_600_000
_MAX_TRANSACTION_RETRY_LIMIT: int = 10
_SCHEMA_VERSION: int = 1
_MIGRATION_LOCK_ID: int = 7_218_786_101
_HISTORY_LOCK_ID: int = 7_218_786_102
_EVENT_CURSOR_PREFIX: str = "postgres-event:"
_RUN_CURSOR_PREFIX: str = "postgres-run:"
_RUN_CURSOR_PART_COUNT: int = 3
_RETRYABLE_SQLSTATES: frozenset[str] = frozenset(("40001", "40P01"))

_CREATE_SCHEMA: tuple[str, ...] = (
    """CREATE TABLE IF NOT EXISTS sqlbuild_storage_migrations (
        singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
        schema_version INTEGER NOT NULL,
        storage_namespace TEXT NOT NULL,
        migrated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS sqlbuild_event_log (
        storage_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        event_id TEXT NOT NULL UNIQUE,
        schema_version INTEGER NOT NULL,
        producer TEXT,
        producer_version TEXT,
        event_type TEXT,
        occurred_at TIMESTAMPTZ,
        received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        invocation_id TEXT,
        run_id TEXT,
        resource_id TEXT,
        resource_attempt_id TEXT,
        operation_id TEXT,
        statement_id TEXT,
        payload_json TEXT NOT NULL,
        content_digest TEXT NOT NULL
    )""",
    """CREATE INDEX IF NOT EXISTS sqlbuild_event_log_run_storage
    ON sqlbuild_event_log (run_id, storage_id)""",
    """CREATE INDEX IF NOT EXISTS sqlbuild_event_log_invocation_storage
    ON sqlbuild_event_log (invocation_id, storage_id)""",
    """CREATE INDEX IF NOT EXISTS sqlbuild_event_log_type_storage
    ON sqlbuild_event_log (event_type, storage_id)""",
    """CREATE TABLE IF NOT EXISTS sqlbuild_run_projection (
        run_id TEXT PRIMARY KEY,
        invocation_id TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        status TEXT NOT NULL,
        is_complete BOOLEAN NOT NULL,
        last_event_cursor TEXT NOT NULL,
        last_event_storage_id BIGINT NOT NULL,
        command TEXT,
        target TEXT,
        environment TEXT,
        started_at TIMESTAMPTZ,
        ended_at TIMESTAMPTZ,
        projection_schema_version INTEGER NOT NULL
    )""",
    """CREATE INDEX IF NOT EXISTS sqlbuild_run_projection_created
    ON sqlbuild_run_projection (created_at, run_id)""",
    """CREATE INDEX IF NOT EXISTS sqlbuild_run_projection_invocation_created
    ON sqlbuild_run_projection (invocation_id, created_at, run_id)""",
)


class PostgresExecutionHistory:
    """PostgreSQL implementation of event-log and run-projection contracts."""

    def __init__(
        self,
        dsn: str,
        *,
        connect_timeout_seconds: int = _CONNECT_TIMEOUT_SECONDS,
        statement_timeout_ms: int = _STATEMENT_TIMEOUT_MS,
        max_transaction_retries: int = _MAX_TRANSACTION_RETRIES,
    ) -> None:
        self._validate_configuration(
            dsn=dsn,
            connect_timeout_seconds=connect_timeout_seconds,
            statement_timeout_ms=statement_timeout_ms,
            max_transaction_retries=max_transaction_retries,
        )
        psycopg, dict_row = self._load_driver()
        self._psycopg: Any = psycopg
        self._max_transaction_retries = max_transaction_retries
        self._closed = False
        self._project_calls = 0
        connection: Any | None = None
        try:
            connection = psycopg.connect(
                dsn,
                connect_timeout=connect_timeout_seconds,
                autocommit=True,
                row_factory=dict_row,
            )
            self._connection: Any = connection
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT set_config('statement_timeout', %s, false)",
                    (str(statement_timeout_ms),),
                )
            self._statement_timeout_ms = statement_timeout_ms
            self._migrate()
            _ = self.reconcile()
        except ExecutionHistoryStorageError:
            self._close_failed_connection(connection=connection)
            self._closed = True
            raise
        except Exception:
            self._close_failed_connection(connection=connection)
            self._closed = True
            raise ExecutionHistoryStorageError(
                "cannot connect to PostgreSQL execution history; verify the secret-resolved DSN, "
                "network access, and sqlbuild[postgres] installation"
            ) from None

    def __repr__(self) -> str:
        state: str = "closed" if self._closed else "open"
        return f"{type(self).__name__}(state={state!r})"

    @property
    def project_calls(self) -> int:
        """Return the number of incremental projection calls."""

        return self._project_calls

    def append_event(self, event: CanonicalLifecycleEvent) -> StoredEvent:
        self._ensure_open()
        return self.append_events((event,))[0]

    def append_events(self, events: Iterable[CanonicalLifecycleEvent]) -> tuple[StoredEvent, ...]:
        self._ensure_open()
        pending: tuple[CanonicalLifecycleEvent, ...] = tuple(events)

        def append(cursor: Any) -> tuple[StoredEvent, ...]:
            self._lock_history(cursor=cursor)
            return self._append_events(cursor=cursor, events=pending)

        return self._transactional(action=append, failure_message="PostgreSQL event append failed")

    def get_events(
        self,
        *,
        event_filter: EventFilter,
        after_cursor: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> EventPage:
        self._ensure_open()
        validate_page_limit(limit)
        after_storage_id: int = self._event_cursor_position(after_cursor)
        conditions: list[str] = ["storage_id > %s"]
        values: list[object] = [after_storage_id]
        conditions, values = self._add_event_filters(
            conditions=conditions, values=values, event_filter=event_filter
        )
        query: str = (
            "SELECT * FROM sqlbuild_event_log WHERE "
            + " AND ".join(conditions)
            + " ORDER BY storage_id ASC LIMIT %s"
        )
        values.append(limit + 1)
        rows: list[Mapping[str, object]] = self._read_rows(query=query, values=values)
        records: tuple[StoredEvent, ...] = tuple(self._stored_event(row) for row in rows[:limit])
        return EventPage(
            records=records,
            next_cursor=records[-1].cursor if records else None,
            has_more=len(rows) > limit,
        )

    def get_run(self, run_id: str) -> RunRecord | None:
        self._ensure_open()
        rows: list[Mapping[str, object]] = self._read_rows(
            query="SELECT * FROM sqlbuild_run_projection WHERE run_id = %s", values=[run_id]
        )
        return None if not rows else self._run_record(rows[0])

    def get_runs(
        self,
        *,
        run_filter: RunFilter,
        after_cursor: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> RunPage:
        self._ensure_open()
        validate_page_limit(limit)
        after_key: tuple[datetime, str] | None = self._run_cursor_key(after_cursor)
        conditions: list[str] = []
        values: list[object] = []
        if after_key is not None:
            conditions.append("(created_at, run_id) > (%s, %s)")
            values.extend(after_key)
        conditions, values = self._add_run_filters(
            conditions=conditions, values=values, run_filter=run_filter
        )
        where: str = " WHERE " + " AND ".join(conditions) if conditions else ""
        values.append(limit + 1)
        rows: list[Mapping[str, object]] = self._read_rows(
            query=(
                f"SELECT * FROM sqlbuild_run_projection{where} ORDER BY created_at, run_id LIMIT %s"
            ),
            values=values,
        )
        records: tuple[RunRecord, ...] = tuple(self._run_record(row) for row in rows[:limit])
        return RunPage(
            records=records,
            next_cursor=self._run_cursor(records[-1]) if records else None,
            has_more=len(rows) > limit,
        )

    def project(self, stored_events: Iterable[StoredEvent]) -> tuple[RunRecord, ...]:
        self._ensure_open()
        pending: tuple[StoredEvent, ...] = tuple(stored_events)
        self._project_calls += 1

        def publish(cursor: Any) -> tuple[RunRecord, ...]:
            self._lock_history(cursor=cursor)
            projected: tuple[RunRecord, ...] = project_runs(
                stored_events=pending, current_runs=self._read_all_runs(cursor=cursor)
            )
            self._replace_projection(cursor=cursor, projected=projected)
            return projected

        return self._transactional(
            action=publish, failure_message="PostgreSQL run projection publication failed"
        )

    def rebuild_from_events(self, stored_events: Iterable[StoredEvent]) -> tuple[RunRecord, ...]:
        self._ensure_open()
        pending: tuple[StoredEvent, ...] = tuple(stored_events)

        def rebuild(cursor: Any) -> tuple[RunRecord, ...]:
            self._lock_history(cursor=cursor)
            projected: tuple[RunRecord, ...] = project_runs(stored_events=pending)
            self._replace_projection(cursor=cursor, projected=projected)
            return projected

        return self._transactional(
            action=rebuild, failure_message="PostgreSQL run projection rebuild failed"
        )

    def append_and_project(
        self, events: Iterable[CanonicalLifecycleEvent]
    ) -> tuple[StoredEvent, ...]:
        """Atomically append immutable facts and publish their run projection."""

        self._ensure_open()
        pending: tuple[CanonicalLifecycleEvent, ...] = tuple(events)

        def append_project(cursor: Any) -> tuple[StoredEvent, ...]:
            self._lock_history(cursor=cursor)
            stored: tuple[StoredEvent, ...] = self._append_events(cursor=cursor, events=pending)
            projected: tuple[RunRecord, ...] = project_runs(
                stored_events=stored, current_runs=self._read_all_runs(cursor=cursor)
            )
            self._replace_projection(cursor=cursor, projected=projected)
            return stored

        return self._transactional(
            action=append_project,
            failure_message="PostgreSQL atomic append and projection failed",
        )

    def reconcile(self) -> tuple[RunRecord, ...]:
        """Rebuild the disposable run projection from all durable event facts."""

        self._ensure_open()

        def reconcile_projection(cursor: Any) -> tuple[RunRecord, ...]:
            self._lock_history(cursor=cursor)
            projected: tuple[RunRecord, ...] = project_runs(
                stored_events=self._read_all_events(cursor=cursor)
            )
            self._replace_projection(cursor=cursor, projected=projected)
            return projected

        return self._transactional(
            action=reconcile_projection, failure_message="PostgreSQL reconciliation failed"
        )

    def check_health(self) -> bool:
        """Verify connectivity and the supported schema revision."""

        self._ensure_open()
        try:
            with self._connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                row: Mapping[str, object] | None = cursor.fetchone()
            return row is not None and self.get_schema_version() == _SCHEMA_VERSION
        except self._psycopg.Error:
            return False

    def get_schema_version(self) -> int:
        self._ensure_open()
        return self._schema_version()

    def upgrade_schema(self, *, target_version: int | None = None) -> int:
        self._ensure_open()
        target: int = _SCHEMA_VERSION if target_version is None else target_version
        if target != _SCHEMA_VERSION:
            raise UnsupportedSchemaVersionError(
                f"unsupported PostgreSQL execution history schema version {target}"
            )
        self._migrate()
        return target

    def close(self) -> None:
        if self._closed:
            return
        self._connection.close()
        self._closed = True

    def dispose(self) -> None:
        self.close()

    def __enter__(self) -> Self:
        self._ensure_open()
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        self.close()
        return None

    @staticmethod
    def _load_driver() -> tuple[Any, Any]:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError:
            raise ExecutionHistoryStorageError(
                "PostgreSQL execution history requires psycopg 3; install sqlbuild[postgres] "
                "or 'psycopg[binary]>=3.2'"
            ) from None
        return psycopg, dict_row

    @staticmethod
    def _validate_configuration(
        *,
        dsn: str,
        connect_timeout_seconds: int,
        statement_timeout_ms: int,
        max_transaction_retries: int,
    ) -> None:
        if not isinstance(dsn, str) or not dsn.strip():
            raise ExecutionHistoryStorageError(
                "PostgreSQL execution history requires an explicit secret-resolved DSN"
            )
        for name, value in (
            ("connect_timeout_seconds", connect_timeout_seconds),
            ("statement_timeout_ms", statement_timeout_ms),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ExecutionHistoryStorageError(f"{name} must be a positive integer")
        if connect_timeout_seconds > _MAX_CONNECT_TIMEOUT_SECONDS:
            raise ExecutionHistoryStorageError(
                f"connect_timeout_seconds must not exceed {_MAX_CONNECT_TIMEOUT_SECONDS}"
            )
        if statement_timeout_ms > _MAX_STATEMENT_TIMEOUT_MS:
            raise ExecutionHistoryStorageError(
                f"statement_timeout_ms must not exceed {_MAX_STATEMENT_TIMEOUT_MS}"
            )
        if (
            isinstance(max_transaction_retries, bool)
            or not isinstance(max_transaction_retries, int)
            or max_transaction_retries < 0
            or max_transaction_retries > _MAX_TRANSACTION_RETRY_LIMIT
        ):
            raise ExecutionHistoryStorageError(
                "max_transaction_retries must be a non-negative integer no greater than "
                f"{_MAX_TRANSACTION_RETRY_LIMIT}"
            )

    @staticmethod
    def _close_failed_connection(*, connection: Any | None) -> None:
        if connection is None:
            return
        try:
            connection.close()
        except Exception:
            pass

    def _migrate(self) -> None:
        def migrate(cursor: Any) -> None:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (_MIGRATION_LOCK_ID,))
            current: int = self._schema_version(cursor=cursor)
            if current > _SCHEMA_VERSION:
                raise UnsupportedSchemaVersionError(
                    f"PostgreSQL execution history schema {current} is newer than supported "
                    f"{_SCHEMA_VERSION}"
                )
            if current < 0:
                raise UnsupportedSchemaVersionError(
                    f"unsupported PostgreSQL execution history schema version {current}"
                )
            if current == _SCHEMA_VERSION:
                return
            for statement in _CREATE_SCHEMA:
                cursor.execute(statement)
            cursor.execute(
                """INSERT INTO sqlbuild_storage_migrations
                (singleton, schema_version, storage_namespace)
                VALUES (TRUE, %s, %s)
                ON CONFLICT (singleton) DO UPDATE SET
                    schema_version = EXCLUDED.schema_version,
                    migrated_at = CURRENT_TIMESTAMP""",
                (_SCHEMA_VERSION, uuid4().hex),
            )

        _ = self._transactional(
            action=migrate, failure_message="PostgreSQL execution history schema migration failed"
        )

    def _schema_version(self, *, cursor: Any | None = None) -> int:
        owns_cursor: bool = cursor is None
        active: Any = cursor
        if active is None:
            active = self._connection.cursor()
        try:
            active.execute("SELECT to_regclass('sqlbuild_storage_migrations') AS table_name")
            exists: Mapping[str, object] | None = active.fetchone()
            if exists is None or exists["table_name"] is None:
                return 0
            active.execute(
                "SELECT schema_version FROM sqlbuild_storage_migrations WHERE singleton = TRUE"
            )
            row: Mapping[str, object] | None = active.fetchone()
            if row is None or isinstance(row["schema_version"], bool):
                raise ExecutionHistoryStorageError(
                    "PostgreSQL execution history schema metadata is invalid"
                )
            value: object = row["schema_version"]
            if not isinstance(value, int):
                raise ExecutionHistoryStorageError(
                    "PostgreSQL execution history schema metadata is invalid"
                )
            return value
        except ExecutionHistoryStorageError:
            raise
        except Exception:
            raise ExecutionHistoryStorageError(
                "PostgreSQL execution history schema metadata is invalid"
            ) from None
        finally:
            if owns_cursor:
                active.close()

    def _namespace(self, *, cursor: Any | None = None) -> str:
        owns_cursor: bool = cursor is None
        active: Any = cursor
        if active is None:
            active = self._connection.cursor()
        try:
            active.execute(
                "SELECT storage_namespace FROM sqlbuild_storage_migrations WHERE singleton = TRUE"
            )
            row: Mapping[str, object] | None = active.fetchone()
            if row is None or not isinstance(row["storage_namespace"], str):
                raise ExecutionHistoryStorageError(
                    "PostgreSQL execution history cursor namespace is missing"
                )
            return row["storage_namespace"]
        finally:
            if owns_cursor:
                active.close()

    def _transactional[Result](
        self, *, action: Callable[[Any], Result], failure_message: str
    ) -> Result:
        attempts = 0
        while True:
            try:
                with self._connection.transaction():
                    with self._connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT set_config('statement_timeout', %s, true)",
                            (str(self._statement_timeout_ms),),
                        )
                        return action(cursor)
            except (IntegrityConflictError, UnsupportedSchemaVersionError):
                raise
            except ExecutionHistoryStorageError:
                raise
            except self._psycopg.Error as error:
                can_retry: bool = (
                    error.sqlstate in _RETRYABLE_SQLSTATES
                    and attempts < self._max_transaction_retries
                )
                if can_retry:
                    attempts += 1
                    continue
                raise ExecutionHistoryStorageError(failure_message) from None

    def _append_events(
        self, *, cursor: Any, events: tuple[CanonicalLifecycleEvent, ...]
    ) -> tuple[StoredEvent, ...]:
        prepared: list[tuple[CanonicalLifecycleEvent, str, str, str]] = []
        batch_content: dict[str, str] = {}
        for event in events:
            event_id: str = canonical_event_id(event)
            content: str = canonical_event_content(event)
            digest: str = hashlib.sha256(content.encode()).hexdigest()
            previous: str | None = batch_content.get(event_id)
            if previous is not None and previous != digest:
                raise IntegrityConflictError(
                    f"event_id {event_id!r} has different canonical content within batch"
                )
            batch_content[event_id] = digest
            prepared.append((event, event_id, content, digest))
        stored: list[StoredEvent] = []
        for event, event_id, content, digest in prepared:
            envelope: dict[str, object | None] = self._event_envelope(event)
            cursor.execute(
                """INSERT INTO sqlbuild_event_log (
                    event_id, schema_version, producer, producer_version, event_type, occurred_at,
                    invocation_id, run_id, resource_id, resource_attempt_id, operation_id,
                    statement_id, payload_json, content_digest
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (event_id) DO NOTHING RETURNING *""",
                (
                    event_id,
                    envelope["schema_version"],
                    envelope["producer"],
                    envelope["producer_version"],
                    envelope["event_type"],
                    envelope["occurred_at"],
                    envelope["invocation_id"],
                    envelope["run_id"],
                    envelope["resource_id"],
                    envelope["resource_attempt_id"],
                    envelope["operation_id"],
                    envelope["statement_id"],
                    content,
                    digest,
                ),
            )
            row: Mapping[str, object] | None = cursor.fetchone()
            if row is None:
                cursor.execute("SELECT * FROM sqlbuild_event_log WHERE event_id = %s", (event_id,))
                row = cursor.fetchone()
            if row is None:
                raise ExecutionHistoryStorageError(
                    "PostgreSQL event append did not produce a durable fact"
                )
            if row["content_digest"] != digest or row["payload_json"] != content:
                raise IntegrityConflictError(
                    f"event_id {event_id!r} has different canonical content"
                )
            stored.append(self._stored_event(row))
        return tuple(stored)

    def _event_envelope(self, event: CanonicalLifecycleEvent) -> dict[str, object | None]:
        if isinstance(event, LifecycleEvent):
            return {
                "schema_version": event.schema_version,
                "producer": event.producer,
                "producer_version": event.producer_version,
                "event_type": event.event_type,
                "occurred_at": event.occurred_at,
                "invocation_id": event.invocation_id,
                "run_id": event.run_id,
                "resource_id": event.resource_id,
                "resource_attempt_id": event.resource_attempt_id,
                "operation_id": event.operation_id,
                "statement_id": event.statement_id,
            }
        raw: Mapping[str, object] = event.raw
        return {
            "schema_version": self._typed_int(raw=raw, field_name="schema_version", default=1),
            "producer": self._typed_text(raw=raw, field_name="producer"),
            "producer_version": self._typed_text(raw=raw, field_name="producer_version"),
            "event_type": self._typed_text(raw=raw, field_name="event_type"),
            "occurred_at": self._opaque_timestamp(event),
            "invocation_id": self._typed_text(raw=raw, field_name="invocation_id"),
            "run_id": self._typed_text(raw=raw, field_name="run_id"),
            "resource_id": self._typed_text(raw=raw, field_name="resource_id"),
            "resource_attempt_id": self._typed_text(raw=raw, field_name="resource_attempt_id"),
            "operation_id": self._typed_text(raw=raw, field_name="operation_id"),
            "statement_id": self._typed_text(raw=raw, field_name="statement_id"),
        }

    @staticmethod
    def _typed_text(*, raw: Mapping[str, object], field_name: str) -> str | None:
        value: object = raw.get(field_name)
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _typed_int(*, raw: Mapping[str, object], field_name: str, default: int) -> int:
        value: object = raw.get(field_name)
        return value if isinstance(value, int) and not isinstance(value, bool) else default

    @staticmethod
    def _opaque_timestamp(event: OpaqueLifecycleEvent) -> datetime | None:
        value: object = event.raw.get("occurred_at")
        if not isinstance(value, str):
            return None
        try:
            parsed: datetime = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        offset: timedelta | None = parsed.utcoffset()
        if offset is None or offset.total_seconds() != 0:
            return None
        return parsed.astimezone(UTC)

    def _stored_event(self, row: Mapping[str, object]) -> StoredEvent:
        raw_storage_id: object = row["storage_id"]
        if not isinstance(raw_storage_id, int) or isinstance(raw_storage_id, bool):
            raise ExecutionHistoryStorageError("PostgreSQL event storage position is invalid")
        storage_id: int = raw_storage_id
        received_at: object = row["received_at"]
        if not isinstance(received_at, datetime):
            raise ExecutionHistoryStorageError("PostgreSQL event timestamp is invalid")
        payload_json: object = row["payload_json"]
        if not isinstance(payload_json, str):
            raise ExecutionHistoryStorageError("PostgreSQL canonical event content is invalid")
        return StoredEvent(
            storage_order=storage_id,
            cursor=self._event_cursor(storage_id),
            received_at=received_at.astimezone(UTC),
            event=lifecycle_event_from_json(payload_json),
        )

    def _event_cursor(self, storage_id: int) -> str:
        return f"{_EVENT_CURSOR_PREFIX}{self._namespace()}:{storage_id}"

    def _event_cursor_position(self, cursor: str | None) -> int:
        if cursor is None:
            return 0
        try:
            prefix, namespace, raw_position = cursor.rsplit(":", 2)
            position: int = int(raw_position)
        except (AttributeError, ValueError):
            raise InvalidCursorError(
                "event cursor is malformed or belongs to another backend"
            ) from None
        if prefix + ":" != _EVENT_CURSOR_PREFIX or namespace != self._namespace() or position < 1:
            raise InvalidCursorError("event cursor is not valid for this storage")
        rows: list[Mapping[str, object]] = self._read_rows(
            query="SELECT 1 AS present FROM sqlbuild_event_log WHERE storage_id = %s",
            values=[position],
        )
        if not rows:
            raise InvalidCursorError("event cursor does not identify a durable event")
        return position

    @staticmethod
    def _add_event_filters(
        *, conditions: list[str], values: list[object], event_filter: EventFilter
    ) -> tuple[list[str], list[object]]:
        filtered_conditions: list[str] = [*conditions]
        filtered_values: list[object] = [*values]
        for column, value in (
            ("invocation_id", event_filter.invocation_id),
            ("run_id", event_filter.run_id),
            ("producer", event_filter.producer),
        ):
            if value is not None:
                filtered_conditions.append(f"{column} = %s")
                filtered_values.append(value)
        if event_filter.event_types:
            filtered_conditions.append("event_type = ANY(%s)")
            filtered_values.append(list(event_filter.event_types))
        if event_filter.family is not None:
            filtered_conditions.append("event_type LIKE %s")
            filtered_values.append(f"{event_filter.family.value}_%")
        if event_filter.occurred_at_start is not None:
            filtered_conditions.append("occurred_at >= %s")
            filtered_values.append(event_filter.occurred_at_start)
        if event_filter.occurred_at_end is not None:
            filtered_conditions.append("occurred_at <= %s")
            filtered_values.append(event_filter.occurred_at_end)
        return filtered_conditions, filtered_values

    def _read_all_events(self, *, cursor: Any) -> tuple[StoredEvent, ...]:
        cursor.execute("SELECT * FROM sqlbuild_event_log ORDER BY storage_id")
        rows: list[Mapping[str, object]] = cursor.fetchall()
        return tuple(self._stored_event(row) for row in rows)

    def _read_all_runs(self, *, cursor: Any) -> tuple[RunRecord, ...]:
        cursor.execute("SELECT * FROM sqlbuild_run_projection ORDER BY created_at, run_id")
        rows: list[Mapping[str, object]] = cursor.fetchall()
        return tuple(self._run_record(row) for row in rows)

    def _replace_projection(self, *, cursor: Any, projected: tuple[RunRecord, ...]) -> None:
        cursor.execute("DELETE FROM sqlbuild_run_projection")
        for run in projected:
            cursor.execute(
                """INSERT INTO sqlbuild_run_projection (
                    run_id, invocation_id, created_at, status, is_complete, last_event_cursor,
                    last_event_storage_id, command, target, environment, started_at, ended_at,
                    projection_schema_version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                self._run_values(run),
            )

    @staticmethod
    def _run_values(run: RunRecord) -> tuple[object, ...]:
        return (
            run.run_id,
            run.invocation_id,
            run.created_at,
            run.status.value,
            run.is_complete,
            run.last_event_cursor,
            run.last_storage_order,
            run.command,
            run.target,
            run.environment,
            run.started_at,
            run.ended_at,
            CURRENT_RUN_STORAGE_SCHEMA_VERSION,
        )

    @staticmethod
    def _run_record(row: Mapping[str, object]) -> RunRecord:
        created_at: object = row["created_at"]
        started_at: object = row["started_at"]
        ended_at: object = row["ended_at"]
        if not isinstance(created_at, datetime):
            raise ExecutionHistoryStorageError("PostgreSQL run timestamp is invalid")
        last_storage_order: object = row["last_event_storage_id"]
        if not isinstance(last_storage_order, int) or isinstance(last_storage_order, bool):
            raise ExecutionHistoryStorageError("PostgreSQL run storage position is invalid")
        return RunRecord(
            run_id=str(row["run_id"]),
            invocation_id=str(row["invocation_id"]),
            created_at=created_at.astimezone(UTC),
            status=RunStatus(str(row["status"])),
            is_complete=bool(row["is_complete"]),
            last_event_cursor=str(row["last_event_cursor"]),
            last_storage_order=last_storage_order,
            command=None if row["command"] is None else str(row["command"]),
            target=None if row["target"] is None else str(row["target"]),
            environment=None if row["environment"] is None else str(row["environment"]),
            started_at=started_at.astimezone(UTC) if isinstance(started_at, datetime) else None,
            ended_at=ended_at.astimezone(UTC) if isinstance(ended_at, datetime) else None,
        )

    def _run_cursor(self, run: RunRecord) -> str:
        payload: str = json.dumps(
            [self._namespace(), run.created_at.isoformat(), run.run_id],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return _RUN_CURSOR_PREFIX + base64.urlsafe_b64encode(payload.encode()).decode()

    def _run_cursor_key(self, cursor: str | None) -> tuple[datetime, str] | None:
        if cursor is None:
            return None
        if not cursor.startswith(_RUN_CURSOR_PREFIX):
            raise InvalidCursorError("run cursor is malformed or belongs to another backend")
        try:
            decoded: object = json.loads(
                base64.urlsafe_b64decode(cursor.removeprefix(_RUN_CURSOR_PREFIX)).decode()
            )
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError, binascii.Error):
            raise InvalidCursorError(
                "run cursor is malformed or belongs to another backend"
            ) from None
        if not isinstance(decoded, list) or len(decoded) != _RUN_CURSOR_PART_COUNT:
            raise InvalidCursorError("run cursor is malformed or belongs to another backend")
        namespace, created_raw, run_id = decoded
        if namespace != self._namespace() or not isinstance(created_raw, str):
            raise InvalidCursorError("run cursor is malformed or belongs to another backend")
        if not isinstance(run_id, str) or not run_id:
            raise InvalidCursorError("run cursor is malformed or belongs to another backend")
        try:
            created_at: datetime = datetime.fromisoformat(created_raw)
        except ValueError:
            raise InvalidCursorError("run cursor contains an invalid timestamp") from None
        if created_at.utcoffset() is None:
            raise InvalidCursorError("run cursor contains an invalid timestamp")
        normalized: datetime = created_at.astimezone(UTC)
        rows: list[Mapping[str, object]] = self._read_rows(
            query=(
                "SELECT 1 AS present FROM sqlbuild_run_projection "
                "WHERE created_at = %s AND run_id = %s"
            ),
            values=[normalized, run_id],
        )
        if not rows:
            raise InvalidCursorError("run cursor does not identify a run in this storage")
        return normalized, run_id

    @staticmethod
    def _add_run_filters(
        *, conditions: list[str], values: list[object], run_filter: RunFilter
    ) -> tuple[list[str], list[object]]:
        filtered_conditions: list[str] = [*conditions]
        filtered_values: list[object] = [*values]
        if run_filter.invocation_id is not None:
            filtered_conditions.append("invocation_id = %s")
            filtered_values.append(run_filter.invocation_id)
        if run_filter.statuses:
            filtered_conditions.append("status = ANY(%s)")
            filtered_values.append([status.value for status in run_filter.statuses])
        if run_filter.created_at_start is not None:
            filtered_conditions.append("created_at >= %s")
            filtered_values.append(run_filter.created_at_start)
        if run_filter.created_at_end is not None:
            filtered_conditions.append("created_at <= %s")
            filtered_values.append(run_filter.created_at_end)
        return filtered_conditions, filtered_values

    def _read_rows(self, *, query: str, values: list[object]) -> list[Mapping[str, object]]:
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(query, values)
                return cursor.fetchall()
        except self._psycopg.Error:
            raise ExecutionHistoryStorageError("PostgreSQL execution history read failed") from None

    @staticmethod
    def _lock_history(*, cursor: Any) -> None:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", (_HISTORY_LOCK_ID,))

    def _ensure_open(self) -> None:
        if self._closed:
            raise ExecutionHistoryStorageError("PostgreSQL execution history storage is closed")
