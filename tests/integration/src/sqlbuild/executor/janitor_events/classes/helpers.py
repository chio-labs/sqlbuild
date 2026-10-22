"""Synthetic janitor events and a statement-recording executor for event writer tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.executor.janitor_events.classes.janitor_event_writer import JanitorEventWriter
from sqlbuild.executor.janitor_events.constants import JANITOR_EVENT_SCHEMA_VERSION
from sqlbuild.executor.janitor_events.main.janitor_event_id import build_janitor_event_id
from sqlbuild.executor.janitor_events.models import JanitorEventRecord
from sqlbuild.executor.janitor_events.types import JanitorEventType

RUN_ID: str = "run_orders_cleanup"
ARCHIVED_AT: datetime = datetime(2026, 9, 24, 10, 15, 0, tzinfo=UTC)


def archive_event(index: int) -> JanitorEventRecord:
    """The archive event of the synthetic relation `orders_<index>` in schema `main`."""

    archive_name: str = f"_sqb_archive__20260924t101500z__orders_{index:04d}"
    return JanitorEventRecord(
        event_id=build_janitor_event_id(
            event_type=JanitorEventType.ARCHIVE,
            run_id=RUN_ID,
            relation_database=None,
            relation_schema="main",
            archive_name=archive_name,
        ),
        schema_version=JANITOR_EVENT_SCHEMA_VERSION,
        event_type=JanitorEventType.ARCHIVE,
        occurred_at=ARCHIVED_AT,
        run_id=RUN_ID,
        relation_database=None,
        relation_schema="main",
        relation_type="BASE TABLE",
        original_name=f"orders_{index:04d}",
        original_qualified_name=f"main.orders_{index:04d}",
        archive_name=archive_name,
        archive_qualified_name=f"main.{archive_name}",
        archived_at=ARCHIVED_AT,
    )


class RecordingExecute:
    """An adapter's `execute` that remembers every statement it ran."""

    def __init__(self, adapter: DuckDbAdapter) -> None:
        self.adapter: DuckDbAdapter = adapter
        self.statements: list[str] = []

    def __call__(self, *, connection: Any, sql: str) -> Any:
        self.statements.append(sql)
        return self.adapter.execute(connection=connection, sql=sql)


def event_writer(execute: RecordingExecute) -> JanitorEventWriter:
    """A writer for `RUN_ID` on `execute`."""

    return JanitorEventWriter(
        execute=execute,
        render_qualified_name=execute.adapter.render_qualified_name,
        run_id=RUN_ID,
    )
