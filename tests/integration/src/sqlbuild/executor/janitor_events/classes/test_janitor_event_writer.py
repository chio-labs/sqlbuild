"""DuckDB integration tests for chunked, append-only janitor audit events."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.executor.janitor_events.classes.janitor_event_writer import JanitorEventWriter
from sqlbuild.executor.janitor_events.constants import (
    JANITOR_EVENT_COLUMNS,
    JANITOR_EVENT_SCHEMA_VERSION,
)
from sqlbuild.executor.janitor_events.main.janitor_event_id import build_janitor_event_id
from sqlbuild.executor.janitor_events.models import JanitorEventRecord
from sqlbuild.executor.janitor_events.types import JanitorEventType
from tests.integration.src.sqlbuild.executor.janitor_events.classes._test_types import (
    JanitorEventWriterTestCase,
)

RUN_ID: str = "run_orders_cleanup"
ARCHIVED_AT: datetime = datetime(2026, 9, 24, 10, 15, 0, tzinfo=UTC)


def _record(index: int) -> JanitorEventRecord:
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


class _RecordingExecute:
    def __init__(self, adapter: DuckDbAdapter) -> None:
        self.adapter: DuckDbAdapter = adapter
        self.statements: list[str] = []

    def __call__(self, *, connection: Any, sql: str) -> Any:
        self.statements.append(sql)
        return self.adapter.execute(connection=connection, sql=sql)


def _writer(execute: _RecordingExecute) -> JanitorEventWriter:
    return JanitorEventWriter(
        execute=execute,
        render_qualified_name=execute.adapter.render_qualified_name,
        run_id=RUN_ID,
    )


@pytest.mark.parametrize(
    "test_case",
    (
        JanitorEventWriterTestCase(
            description="events past one chunk are appended with one insert per chunk",
            record_count=250,
            written_before=0,
            write_now_first=False,
            expected_row_count=250,
            expected_insert_count=3,
            expected_existence_query_count=1,
        ),
        JanitorEventWriterTestCase(
            description="a retried run skips every event it already wrote",
            record_count=5,
            written_before=5,
            write_now_first=False,
            expected_row_count=5,
            expected_insert_count=0,
            expected_existence_query_count=1,
        ),
        JanitorEventWriterTestCase(
            description="a retried run appends only the events it had not written",
            record_count=5,
            written_before=3,
            write_now_first=False,
            expected_row_count=5,
            expected_insert_count=1,
            expected_existence_query_count=1,
        ),
        JanitorEventWriterTestCase(
            description="an event written at once is not held for the next flush",
            record_count=1,
            written_before=0,
            write_now_first=True,
            expected_row_count=1,
            expected_insert_count=1,
            expected_existence_query_count=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_janitor_events_when_writing_in_chunks_then_each_event_is_appended_once(
    test_case: JanitorEventWriterTestCase,
    tmp_path: Path,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "janitor_events.duckdb")})
    records: tuple[JanitorEventRecord, ...] = tuple(
        _record(index) for index in range(test_case.record_count)
    )
    try:
        adapter.execute(
            connection=connection,
            sql=adapter.render_create_janitor_event_table_sql(database=None, schema="main"),
        )
        earlier: JanitorEventWriter = _writer(_RecordingExecute(adapter))
        for record in records[: test_case.written_before]:
            earlier.add(record)
        earlier.flush(connection=connection)
        execute: _RecordingExecute = _RecordingExecute(adapter)
        writer: JanitorEventWriter = _writer(execute)
        writer.read_existing(connection=connection, schemas=((None, "main"),))
        if test_case.write_now_first:
            writer.write_now(connection=connection, record=records[0])
        for record in records:
            writer.add(record)
        writer.flush(connection=connection)
        rows: list[tuple[object, ...]] = connection.execute(
            f"SELECT {', '.join(JANITOR_EVENT_COLUMNS)} FROM main._sqlbuild_janitor_events "
            "ORDER BY archive_name"
        ).fetchall()
    finally:
        adapter.close(connection)

    assert len(rows) == test_case.expected_row_count
    assert len({row[0] for row in rows}) == test_case.expected_row_count
    assert rows[0] == (
        records[0].event_id,
        JANITOR_EVENT_SCHEMA_VERSION,
        "archive",
        ARCHIVED_AT.replace(tzinfo=None),
        RUN_ID,
        None,
        "main",
        "BASE TABLE",
        "orders_0000",
        "main.orders_0000",
        records[0].archive_name,
        f"main.{records[0].archive_name}",
        ARCHIVED_AT.replace(tzinfo=None),
    )
    assert sum(sql.startswith("INSERT INTO") for sql in execute.statements) == (
        test_case.expected_insert_count
    )
    assert sum(sql.startswith("SELECT") for sql in execute.statements) == (
        test_case.expected_existence_query_count
    )
