"""Append-only janitor audit events, written in chunks per schema event table."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.contract.types import AdapterExecute
from sqlbuild.executor.janitor_events._helpers.sql import (
    build_existing_run_events_sql,
    build_insert_many_sql,
)
from sqlbuild.executor.janitor_events.constants import JANITOR_EVENT_CHUNK_SIZE
from sqlbuild.executor.janitor_events.models import JanitorEventRecord

type _SchemaKey = tuple[str | None, str]


class JanitorEventWriter:
    """Write each event at most once, reading the run's existing event IDs once per schema.

    Events wait in memory until `flush`, which appends each schema's pending events with one
    multi-row INSERT per chunk. `write_now` appends one event at once. Event IDs are
    deterministic per run, so an ID already present is never inserted again, including when the
    same invocation is retried.
    """

    def __init__(
        self,
        *,
        execute: AdapterExecute[Any, Any],
        render_qualified_name: Callable[..., str | None],
        run_id: str,
    ) -> None:
        self._execute: AdapterExecute[Any, Any] = execute
        self._render_qualified_name: Callable[..., str | None] = render_qualified_name
        self._run_id: str = run_id
        self._written: set[str] = set()
        self._pending: dict[_SchemaKey, list[JanitorEventRecord]] = {}
        self._lock: threading.Lock = threading.Lock()

    def read_existing(self, *, connection: Any, schemas: tuple[_SchemaKey, ...]) -> None:
        """Remember the IDs of events this run already wrote to each schema's table."""

        database: str | None
        schema: str
        for database, schema in schemas:
            cursor: Any = self._execute(
                connection=connection,
                sql=build_existing_run_events_sql(
                    database=database,
                    schema=schema,
                    run_id=self._run_id,
                    render_qualified_name=self._render_qualified_name,
                ),
            )
            self._written.update(str(row[0]) for row in cursor.fetchall())

    def add(self, record: JanitorEventRecord) -> None:
        """Hold one event until the next `flush`, unless it is already written or held."""

        with self._lock:
            if record.event_id in self._written or any(
                held.event_id == record.event_id
                for held in self._pending.get(_schema_key(record), ())
            ):
                return
            self._pending.setdefault(_schema_key(record), []).append(record)

    def write_now(self, *, connection: Any, record: JanitorEventRecord) -> None:
        """Append one event immediately on `connection`, unless it is already written."""

        with self._lock:
            if record.event_id in self._written:
                return
            self._written.add(record.event_id)
        try:
            self._insert(connection=connection, records=(record,))
        except BaseException:
            with self._lock:
                self._written.discard(record.event_id)
            raise

    def flush(self, *, connection: Any) -> None:
        """Append every held event, one INSERT per schema and chunk of rows."""

        with self._lock:
            pending: dict[_SchemaKey, list[JanitorEventRecord]] = self._pending
            self._pending = {}
        try:
            key: _SchemaKey
            records: list[JanitorEventRecord]
            for key, records in list(pending.items()):
                while records:
                    chunk: tuple[JanitorEventRecord, ...] = tuple(
                        records[:JANITOR_EVENT_CHUNK_SIZE]
                    )
                    self._insert(connection=connection, records=chunk)
                    del records[: len(chunk)]
                    with self._lock:
                        self._written.update(record.event_id for record in chunk)
                del pending[key]
        finally:
            if pending:
                with self._lock:
                    for key, records in pending.items():
                        self._pending.setdefault(key, [])[:0] = records

    def _insert(self, *, connection: Any, records: tuple[JanitorEventRecord, ...]) -> None:
        _ = self._execute(
            connection=connection,
            sql=build_insert_many_sql(
                records=records, render_qualified_name=self._render_qualified_name
            ),
        )


def _schema_key(record: JanitorEventRecord) -> _SchemaKey:
    return (record.relation_database, record.relation_schema)
