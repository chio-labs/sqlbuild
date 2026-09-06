"""Project-local SQLite execution history storage."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import sqlite3
import threading
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import TracebackType
from typing import Self
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

_BUSY_TIMEOUT_MS: int = 5_000
_CURSOR_PREFIX: str = "sqlite-event:"
_RUN_CURSOR_PREFIX: str = "sqlite-run:"
_SCHEMA_VERSION: int = 1
_MEMORY_PATH: str = ":memory:"
_HEALTHY_CHECK_RESULT: str = "ok"
_RUN_CURSOR_PART_COUNT: int = 3

_CREATE_SCHEMA: str = """
CREATE TABLE IF NOT EXISTS execution_history_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS lifecycle_event_log (
    storage_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    schema_version INTEGER NOT NULL,
    producer TEXT,
    event_type TEXT,
    occurred_at TEXT,
    received_at TEXT NOT NULL,
    invocation_id TEXT,
    run_id TEXT,
    resource_id TEXT,
    resource_attempt_id TEXT,
    operation_id TEXT,
    statement_id TEXT,
    payload_json TEXT NOT NULL,
    content_digest TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS lifecycle_event_log_run_storage
    ON lifecycle_event_log (run_id, storage_id);
CREATE INDEX IF NOT EXISTS lifecycle_event_log_invocation_storage
    ON lifecycle_event_log (invocation_id, storage_id);
CREATE INDEX IF NOT EXISTS lifecycle_event_log_type_storage
    ON lifecycle_event_log (event_type, storage_id);
CREATE TABLE IF NOT EXISTS run_projection (
    run_id TEXT PRIMARY KEY,
    invocation_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    is_complete INTEGER NOT NULL,
    last_event_cursor TEXT NOT NULL,
    last_storage_order INTEGER NOT NULL,
    command TEXT,
    target TEXT,
    environment TEXT,
    started_at TEXT,
    ended_at TEXT,
    projection_schema_version INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS run_projection_created ON run_projection (created_at, run_id);
CREATE INDEX IF NOT EXISTS run_projection_invocation_created
    ON run_projection (invocation_id, created_at, run_id);
"""


class SQLiteExecutionHistory:
    """SQLite implementation of event-log and run-projection storage contracts."""

    def __init__(
        self,
        project_dir: Path | str | None = None,
        *,
        path: Path | str | None = None,
        busy_timeout_ms: int = _BUSY_TIMEOUT_MS,
    ) -> None:
        if project_dir is not None and path is not None:
            raise ExecutionHistoryStorageError("provide project_dir or path, not both")
        if isinstance(busy_timeout_ms, bool) or not isinstance(busy_timeout_ms, int):
            raise ExecutionHistoryStorageError("busy_timeout_ms must be a positive integer")
        if busy_timeout_ms < 1:
            raise ExecutionHistoryStorageError("busy_timeout_ms must be a positive integer")
        selected: Path | str = (
            path if path is not None else Path.cwd() if project_dir is None else project_dir
        )
        self._path: str = (
            selected
            if isinstance(selected, str) and selected == _MEMORY_PATH
            else str(Path(selected) / ".sqlbuild" / "history.sqlite3")
            if path is None
            else str(Path(selected))
        )
        self._closed = False
        self._project_calls = 0
        self._lock: threading.RLock = threading.RLock()
        connection: sqlite3.Connection | None = None
        try:
            self._prepare_parent()
            connection = sqlite3.connect(
                self._path,
                timeout=busy_timeout_ms / 1000,
                isolation_level=None,
                check_same_thread=False,
            )
            self._connection: sqlite3.Connection = connection
            with self._lock:
                self._connection.row_factory = sqlite3.Row
                _ = self._connection.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
                _ = self._connection.execute("PRAGMA foreign_keys = ON")
                if self._path != _MEMORY_PATH:
                    _ = self._connection.execute("PRAGMA journal_mode = WAL").fetchone()
                self._migrate()
            self._restrict_file_permissions()
            _ = self.reconcile()
        except ExecutionHistoryStorageError:
            self._close_failed_connection(connection=connection)
            self._closed = True
            raise
        except (OSError, sqlite3.Error) as error:
            self._close_failed_connection(connection=connection)
            self._closed = True
            raise ExecutionHistoryStorageError(
                f"cannot open SQLite history at {self._path}"
            ) from error

    @property
    def path(self) -> Path | None:
        """Return the database path, or None for an in-memory database."""

        return None if self._path == _MEMORY_PATH else Path(self._path)

    @property
    def project_calls(self) -> int:
        """Return the number of incremental projection calls."""

        with self._lock:
            return self._project_calls

    def append_event(self, event: CanonicalLifecycleEvent) -> StoredEvent:
        with self._lock:
            self._ensure_open()
            return self.append_events((event,))[0]

    def append_events(self, events: Iterable[CanonicalLifecycleEvent]) -> tuple[StoredEvent, ...]:
        with self._lock:
            self._ensure_open()
            pending: tuple[CanonicalLifecycleEvent, ...] = tuple(events)
            try:
                with self._transaction():
                    return self._append_events(pending)
            except IntegrityConflictError:
                raise
            except sqlite3.Error as error:
                raise ExecutionHistoryStorageError("SQLite event append failed") from error

    def get_events(
        self,
        *,
        event_filter: EventFilter,
        after_cursor: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> EventPage:
        with self._lock:
            self._ensure_open()
            validate_page_limit(limit)
            after_storage_id: int = self._event_cursor_position(after_cursor)
            conditions: list[str] = ["storage_id > ?"]
            values: list[object] = [after_storage_id]
            conditions, values = self._add_event_filters(
                conditions=conditions, values=values, event_filter=event_filter
            )
            sql: str = (
                "SELECT * FROM lifecycle_event_log WHERE "
                + " AND ".join(conditions)
                + " ORDER BY storage_id ASC LIMIT ?"
            )
            values.append(limit + 1)
            try:
                rows: list[sqlite3.Row] = list(self._connection.execute(sql, values))
            except sqlite3.Error as error:
                raise ExecutionHistoryStorageError("SQLite event read failed") from error
            records: tuple[StoredEvent, ...] = tuple(
                self._stored_event(row) for row in rows[:limit]
            )
            return EventPage(
                records=records,
                next_cursor=records[-1].cursor if records else None,
                has_more=len(rows) > limit,
            )

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._lock:
            self._ensure_open()
            row: sqlite3.Row | None = self._connection.execute(
                "SELECT * FROM run_projection WHERE run_id = ?", (run_id,)
            ).fetchone()
            return None if row is None else self._run_record(row)

    def get_runs(
        self,
        *,
        run_filter: RunFilter,
        after_cursor: str | None = None,
        limit: int = DEFAULT_PAGE_LIMIT,
    ) -> RunPage:
        with self._lock:
            self._ensure_open()
            validate_page_limit(limit)
            after_key: tuple[str, str] | None = self._run_cursor_key(after_cursor)
            conditions: list[str] = []
            values: list[object] = []
            if after_key is not None:
                conditions.append("(created_at > ? OR (created_at = ? AND run_id > ?))")
                values.extend((after_key[0], after_key[0], after_key[1]))
            conditions, values = self._add_run_filters(
                conditions=conditions, values=values, run_filter=run_filter
            )
            where: str = " WHERE " + " AND ".join(conditions) if conditions else ""
            values.append(limit + 1)
            rows: list[sqlite3.Row] = list(
                self._connection.execute(
                    f"SELECT * FROM run_projection{where} ORDER BY created_at, run_id LIMIT ?",
                    values,
                )
            )
            records: tuple[RunRecord, ...] = tuple(self._run_record(row) for row in rows[:limit])
            return RunPage(
                records=records,
                next_cursor=self._run_cursor(records[-1]) if records else None,
                has_more=len(rows) > limit,
            )

    def project(self, stored_events: Iterable[StoredEvent]) -> tuple[RunRecord, ...]:
        with self._lock:
            self._ensure_open()
            self._project_calls += 1
            current: tuple[RunRecord, ...] = self._read_all_runs()
            projected: tuple[RunRecord, ...] = project_runs(
                stored_events=stored_events, current_runs=current
            )
            self._publish_projection(projected)
            return projected

    def rebuild_from_events(self, stored_events: Iterable[StoredEvent]) -> tuple[RunRecord, ...]:
        with self._lock:
            self._ensure_open()
            projected: tuple[RunRecord, ...] = project_runs(stored_events=stored_events)
            self._publish_projection(projected)
            return projected

    def append_and_project(
        self, events: Iterable[CanonicalLifecycleEvent]
    ) -> tuple[StoredEvent, ...]:
        """Atomically append immutable facts and publish their run projection."""

        with self._lock:
            self._ensure_open()
            pending: tuple[CanonicalLifecycleEvent, ...] = tuple(events)
            try:
                with self._transaction():
                    stored: tuple[StoredEvent, ...] = self._append_events(pending)
                    projected: tuple[RunRecord, ...] = project_runs(
                        stored_events=stored, current_runs=self._read_all_runs()
                    )
                    self._replace_projection(projected)
                    return stored
            except IntegrityConflictError:
                raise
            except sqlite3.Error as error:
                raise ExecutionHistoryStorageError(
                    "SQLite atomic append and projection failed"
                ) from error

    def reconcile(self) -> tuple[RunRecord, ...]:
        """Rebuild the disposable run projection from all durable event facts."""

        with self._lock:
            self._ensure_open()
            try:
                with self._transaction():
                    records: tuple[StoredEvent, ...] = self._read_all_events()
                    projected: tuple[RunRecord, ...] = project_runs(stored_events=records)
                    self._replace_projection(projected)
                    return projected
            except sqlite3.Error as error:
                raise ExecutionHistoryStorageError("SQLite reconciliation failed") from error

    def check_health(self) -> bool:
        """Verify connectivity, integrity, and the supported schema revision."""

        with self._lock:
            self._ensure_open()
            result: sqlite3.Row | None = self._connection.execute("PRAGMA quick_check").fetchone()
            return (
                result is not None
                and result[0] == _HEALTHY_CHECK_RESULT
                and self.get_schema_version() == _SCHEMA_VERSION
            )

    def get_schema_version(self) -> int:
        with self._lock:
            self._ensure_open()
            return self._metadata_version()

    def upgrade_schema(self, *, target_version: int | None = None) -> int:
        with self._lock:
            self._ensure_open()
            target: int = _SCHEMA_VERSION if target_version is None else target_version
            if target != _SCHEMA_VERSION:
                raise UnsupportedSchemaVersionError(f"unsupported SQLite schema version {target}")
            self._migrate()
            return target

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            try:
                self._connection.close()
            finally:
                self._closed = True

    def dispose(self) -> None:
        self.close()

    def __enter__(self) -> Self:
        with self._lock:
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

    def _prepare_parent(self) -> None:
        if self._path == _MEMORY_PATH:
            return
        parent: Path = Path(self._path).parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    def _restrict_file_permissions(self) -> None:
        if self._path != _MEMORY_PATH:
            os.chmod(self._path, 0o600)

    @staticmethod
    def _close_failed_connection(*, connection: sqlite3.Connection | None) -> None:
        if connection is None:
            return
        try:
            connection.close()
        except sqlite3.Error:
            pass

    def _migrate(self) -> None:
        current: int = self._metadata_version()
        if current > _SCHEMA_VERSION:
            raise UnsupportedSchemaVersionError(
                f"SQLite history schema {current} is newer than supported {_SCHEMA_VERSION}"
            )
        if current < 0:
            raise UnsupportedSchemaVersionError(f"unsupported SQLite schema version {current}")
        if current == _SCHEMA_VERSION:
            return
        try:
            namespace: str = uuid4().hex
            with self._transaction():
                for statement in _CREATE_SCHEMA.split(";"):
                    if statement.strip():
                        _ = self._connection.execute(statement)
                _ = self._connection.execute(
                    "INSERT OR IGNORE INTO execution_history_metadata(key, value) VALUES (?, ?)",
                    ("storage_namespace", namespace),
                )
                _ = self._connection.execute(
                    "INSERT OR REPLACE INTO execution_history_metadata(key, value) VALUES (?, ?)",
                    ("schema_version", str(_SCHEMA_VERSION)),
                )
        except sqlite3.Error as error:
            raise ExecutionHistoryStorageError("SQLite history schema migration failed") from error

    def _metadata_version(self) -> int:
        exists: sqlite3.Row | None = self._connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("execution_history_metadata",),
        ).fetchone()
        if exists is None:
            return 0
        row: sqlite3.Row | None = self._connection.execute(
            "SELECT value FROM execution_history_metadata WHERE key = ?", ("schema_version",)
        ).fetchone()
        if row is None:
            return 0
        try:
            return int(row[0])
        except (TypeError, ValueError) as error:
            raise ExecutionHistoryStorageError(
                "SQLite history schema metadata is invalid"
            ) from error

    def _namespace(self) -> str:
        row: sqlite3.Row | None = self._connection.execute(
            "SELECT value FROM execution_history_metadata WHERE key = ?", ("storage_namespace",)
        ).fetchone()
        if row is None:
            raise ExecutionHistoryStorageError("SQLite history cursor namespace is missing")
        return str(row[0])

    def _append_events(
        self, events: tuple[CanonicalLifecycleEvent, ...]
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
            existing: sqlite3.Row | None = self._connection.execute(
                "SELECT * FROM lifecycle_event_log WHERE event_id = ?", (event_id,)
            ).fetchone()
            if existing is not None:
                if existing["content_digest"] != digest or existing["payload_json"] != content:
                    raise IntegrityConflictError(
                        f"event_id {event_id!r} has different canonical content"
                    )
                stored.append(self._stored_event(existing))
                continue
            received_at: str = self._timestamp(datetime.now(UTC))
            envelope: dict[str, object | None] = self._event_envelope(event)
            cursor: sqlite3.Cursor = self._connection.execute(
                """INSERT INTO lifecycle_event_log (
                    event_id, schema_version, producer, event_type, occurred_at, received_at,
                    invocation_id, run_id, resource_id, resource_attempt_id, operation_id,
                    statement_id, payload_json, content_digest
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event_id,
                    envelope["schema_version"],
                    envelope["producer"],
                    envelope["event_type"],
                    envelope["occurred_at"],
                    received_at,
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
            row: sqlite3.Row = self._connection.execute(
                "SELECT * FROM lifecycle_event_log WHERE storage_id = ?", (cursor.lastrowid,)
            ).fetchone()
            stored.append(self._stored_event(row))
        return tuple(stored)

    def _event_envelope(self, event: CanonicalLifecycleEvent) -> dict[str, object | None]:
        if isinstance(event, LifecycleEvent):
            return {
                "schema_version": event.schema_version,
                "producer": event.producer,
                "event_type": event.event_type,
                "occurred_at": self._timestamp(event.occurred_at),
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
    def _opaque_timestamp(event: OpaqueLifecycleEvent) -> str | None:
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
        return SQLiteExecutionHistory._timestamp(parsed)

    def _stored_event(self, row: sqlite3.Row) -> StoredEvent:
        storage_id: int = int(row["storage_id"])
        return StoredEvent(
            storage_order=storage_id,
            cursor=self._event_cursor(storage_id),
            received_at=self._parse_timestamp(row["received_at"]),
            event=lifecycle_event_from_json(row["payload_json"]),
        )

    def _event_cursor(self, storage_id: int) -> str:
        return f"{_CURSOR_PREFIX}{self._namespace()}:{storage_id}"

    def _event_cursor_position(self, cursor: str | None) -> int:
        if cursor is None:
            return 0
        try:
            prefix, namespace, raw_position = cursor.rsplit(":", 2)
            position: int = int(raw_position)
        except (AttributeError, ValueError) as error:
            raise InvalidCursorError(
                "event cursor is malformed or belongs to another backend"
            ) from error
        if prefix + ":" != _CURSOR_PREFIX or namespace != self._namespace() or position < 1:
            raise InvalidCursorError("event cursor is not valid for this storage")
        exists: sqlite3.Row | None = self._connection.execute(
            "SELECT 1 FROM lifecycle_event_log WHERE storage_id = ?", (position,)
        ).fetchone()
        if exists is None:
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
                filtered_conditions.append(f"{column} = ?")
                filtered_values.append(value)
        if event_filter.event_types:
            placeholders: str = ",".join("?" for _ in event_filter.event_types)
            filtered_conditions.append(f"event_type IN ({placeholders})")
            filtered_values.extend(event_filter.event_types)
        if event_filter.family is not None:
            filtered_conditions.append("event_type LIKE ?")
            filtered_values.append(f"{event_filter.family.value}_%")
        if event_filter.occurred_at_start is not None:
            filtered_conditions.append("occurred_at >= ?")
            filtered_values.append(
                SQLiteExecutionHistory._timestamp(event_filter.occurred_at_start)
            )
        if event_filter.occurred_at_end is not None:
            filtered_conditions.append("occurred_at <= ?")
            filtered_values.append(SQLiteExecutionHistory._timestamp(event_filter.occurred_at_end))
        return filtered_conditions, filtered_values

    def _read_all_events(self) -> tuple[StoredEvent, ...]:
        rows: list[sqlite3.Row] = list(
            self._connection.execute("SELECT * FROM lifecycle_event_log ORDER BY storage_id")
        )
        return tuple(self._stored_event(row) for row in rows)

    def _read_all_runs(self) -> tuple[RunRecord, ...]:
        rows: list[sqlite3.Row] = list(
            self._connection.execute("SELECT * FROM run_projection ORDER BY created_at, run_id")
        )
        return tuple(self._run_record(row) for row in rows)

    def _publish_projection(self, projected: tuple[RunRecord, ...]) -> None:
        try:
            with self._transaction():
                self._replace_projection(projected)
        except sqlite3.Error as error:
            raise ExecutionHistoryStorageError(
                "SQLite run projection publication failed"
            ) from error

    def _replace_projection(self, projected: tuple[RunRecord, ...]) -> None:
        _ = self._connection.execute("DELETE FROM run_projection")
        self._connection.executemany(
            """INSERT INTO run_projection (
                run_id, invocation_id, created_at, status, is_complete, last_event_cursor,
                last_storage_order, command, target, environment, started_at, ended_at,
                projection_schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            tuple(self._run_values(run) for run in projected),
        )

    @staticmethod
    def _run_values(run: RunRecord) -> tuple[object, ...]:
        return (
            run.run_id,
            run.invocation_id,
            SQLiteExecutionHistory._timestamp(run.created_at),
            run.status.value,
            int(run.is_complete),
            run.last_event_cursor,
            run.last_storage_order,
            run.command,
            run.target,
            run.environment,
            None if run.started_at is None else SQLiteExecutionHistory._timestamp(run.started_at),
            None if run.ended_at is None else SQLiteExecutionHistory._timestamp(run.ended_at),
            CURRENT_RUN_STORAGE_SCHEMA_VERSION,
        )

    @staticmethod
    def _run_record(row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            run_id=row["run_id"],
            invocation_id=row["invocation_id"],
            created_at=SQLiteExecutionHistory._parse_timestamp(row["created_at"]),
            status=RunStatus(row["status"]),
            is_complete=bool(row["is_complete"]),
            last_event_cursor=row["last_event_cursor"],
            last_storage_order=int(row["last_storage_order"]),
            command=row["command"],
            target=row["target"],
            environment=row["environment"],
            started_at=(
                None
                if row["started_at"] is None
                else SQLiteExecutionHistory._parse_timestamp(row["started_at"])
            ),
            ended_at=(
                None
                if row["ended_at"] is None
                else SQLiteExecutionHistory._parse_timestamp(row["ended_at"])
            ),
        )

    def _run_cursor(self, run: RunRecord) -> str:
        payload: str = json.dumps(
            [self._namespace(), self._timestamp(run.created_at), run.run_id],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return _RUN_CURSOR_PREFIX + base64.urlsafe_b64encode(payload.encode()).decode()

    def _run_cursor_key(self, cursor: str | None) -> tuple[str, str] | None:
        if cursor is None:
            return None
        if not cursor.startswith(_RUN_CURSOR_PREFIX):
            raise InvalidCursorError("run cursor is malformed or belongs to another backend")
        try:
            decoded: object = json.loads(
                base64.urlsafe_b64decode(cursor.removeprefix(_RUN_CURSOR_PREFIX)).decode()
            )
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError, binascii.Error) as error:
            raise InvalidCursorError(
                "run cursor is malformed or belongs to another backend"
            ) from error
        if not isinstance(decoded, list) or len(decoded) != _RUN_CURSOR_PART_COUNT:
            raise InvalidCursorError("run cursor is malformed or belongs to another backend")
        namespace, created_at, run_id = decoded
        if namespace != self._namespace() or not isinstance(created_at, str):
            raise InvalidCursorError("run cursor is malformed or belongs to another backend")
        if not isinstance(run_id, str) or not run_id:
            raise InvalidCursorError("run cursor is malformed or belongs to another backend")
        try:
            _ = self._parse_timestamp(created_at)
        except (ValueError, ExecutionHistoryStorageError) as error:
            raise InvalidCursorError("run cursor contains an invalid timestamp") from error
        exists: sqlite3.Row | None = self._connection.execute(
            "SELECT 1 FROM run_projection WHERE created_at = ? AND run_id = ?",
            (created_at, run_id),
        ).fetchone()
        if exists is None:
            raise InvalidCursorError("run cursor does not identify a run in this storage")
        return created_at, run_id

    @staticmethod
    def _add_run_filters(
        *, conditions: list[str], values: list[object], run_filter: RunFilter
    ) -> tuple[list[str], list[object]]:
        filtered_conditions: list[str] = [*conditions]
        filtered_values: list[object] = [*values]
        if run_filter.invocation_id is not None:
            filtered_conditions.append("invocation_id = ?")
            filtered_values.append(run_filter.invocation_id)
        if run_filter.statuses:
            placeholders: str = ",".join("?" for _ in run_filter.statuses)
            filtered_conditions.append(f"status IN ({placeholders})")
            filtered_values.extend(status.value for status in run_filter.statuses)
        if run_filter.created_at_start is not None:
            filtered_conditions.append("created_at >= ?")
            filtered_values.append(SQLiteExecutionHistory._timestamp(run_filter.created_at_start))
        if run_filter.created_at_end is not None:
            filtered_conditions.append("created_at <= ?")
            filtered_values.append(SQLiteExecutionHistory._timestamp(run_filter.created_at_end))
        return filtered_conditions, filtered_values

    @staticmethod
    def _timestamp(value: datetime) -> str:
        return value.astimezone(UTC).isoformat(timespec="microseconds")

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        parsed: datetime = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            raise ExecutionHistoryStorageError("SQLite history timestamp is not timezone-aware")
        return parsed.astimezone(UTC)

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock:
            self._ensure_open()
            _ = self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                try:
                    _ = self._connection.execute("ROLLBACK")
                except BaseException:
                    pass
                raise
            else:
                try:
                    _ = self._connection.execute("COMMIT")
                except sqlite3.Error:
                    if self._connection.in_transaction:
                        try:
                            _ = self._connection.execute("ROLLBACK")
                        except BaseException:
                            pass
                    raise

    def _ensure_open(self) -> None:
        if self._closed:
            raise ExecutionHistoryStorageError("SQLite execution history storage is closed")
