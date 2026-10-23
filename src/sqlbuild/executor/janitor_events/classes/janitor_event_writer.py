"""Append-only janitor audit events, written in multi-row chunks per schema event table."""

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
    """Write each deterministic event ID at most once, even across retries of one invocation."""

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
            ids: set[str] = {str(row[0]) for row in cursor.fetchall()}
            with self._lock:
                self._written |= ids

    def write(self, *, connection: Any, records: tuple[JanitorEventRecord, ...]) -> None:
        """Append the unwritten events, one INSERT per schema and chunk of rows."""

        with self._lock:
            unwritten: dict[str, JanitorEventRecord] = {
                record.event_id: record
                for record in records
                if record.event_id not in self._written
            }
        by_schema: dict[_SchemaKey, list[JanitorEventRecord]] = {}
        record: JanitorEventRecord
        for record in unwritten.values():
            by_schema.setdefault((record.relation_database, record.relation_schema), []).append(
                record
            )
        schema_records: list[JanitorEventRecord]
        for schema_records in by_schema.values():
            start: int
            for start in range(0, len(schema_records), JANITOR_EVENT_CHUNK_SIZE):
                chunk: tuple[JanitorEventRecord, ...] = tuple(
                    schema_records[start : start + JANITOR_EVENT_CHUNK_SIZE]
                )
                _ = self._execute(
                    connection=connection,
                    sql=build_insert_many_sql(
                        records=chunk, render_qualified_name=self._render_qualified_name
                    ),
                )
                with self._lock:
                    self._written |= {written.event_id for written in chunk}
