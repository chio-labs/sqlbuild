"""DuckDB integration tests for chunked, append-only janitor audit events."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.executor.janitor_events.classes.janitor_event_writer import JanitorEventWriter
from sqlbuild.executor.janitor_events.constants import (
    JANITOR_EVENT_COLUMNS,
    JANITOR_EVENT_SCHEMA_VERSION,
)
from sqlbuild.executor.janitor_events.models import JanitorEventRecord
from tests.integration.src.sqlbuild.executor.janitor_events.classes._test_types import (
    JanitorEventWriterTestCase,
)
from tests.integration.src.sqlbuild.executor.janitor_events.classes.helpers import (
    ARCHIVED_AT,
    RUN_ID,
    RecordingExecute,
    archive_event,
    event_writer,
)


@pytest.mark.parametrize(
    "test_case",
    (
        JanitorEventWriterTestCase(
            description="events past one chunk are appended with one insert per chunk",
            record_count=250,
            written_before=0,
            write_passes=1,
            expected_row_count=250,
            expected_insert_count=3,
            expected_existence_query_count=1,
        ),
        JanitorEventWriterTestCase(
            description="a retried run skips every event it already wrote",
            record_count=5,
            written_before=5,
            write_passes=1,
            expected_row_count=5,
            expected_insert_count=0,
            expected_existence_query_count=1,
        ),
        JanitorEventWriterTestCase(
            description="a retried run appends only the events it had not written",
            record_count=5,
            written_before=3,
            write_passes=1,
            expected_row_count=5,
            expected_insert_count=1,
            expected_existence_query_count=1,
        ),
        JanitorEventWriterTestCase(
            description="writing the same events again in one run appends nothing more",
            record_count=4,
            written_before=0,
            write_passes=3,
            expected_row_count=4,
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
        archive_event(index) for index in range(test_case.record_count)
    )
    try:
        adapter.execute(
            connection=connection,
            sql=adapter.render_create_janitor_event_table_sql(database=None, schema="main"),
        )
        event_writer(RecordingExecute(adapter)).write(
            connection=connection, records=records[: test_case.written_before]
        )
        execute: RecordingExecute = RecordingExecute(adapter)
        writer: JanitorEventWriter = event_writer(execute)
        writer.read_existing(connection=connection, schemas=((None, "main"),))
        _: int
        for _ in range(test_case.write_passes):
            writer.write(connection=connection, records=records)
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
