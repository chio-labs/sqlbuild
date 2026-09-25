"""DuckDB integration tests for append-only janitor audit events."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.executor.janitor_events.constants import (
    JANITOR_EVENT_COLUMNS,
    JANITOR_EVENT_SCHEMA_VERSION,
)
from sqlbuild.executor.janitor_events.main.janitor_event_id import build_janitor_event_id
from sqlbuild.executor.janitor_events.main.write_janitor_event import write_janitor_event_record
from sqlbuild.executor.janitor_events.models import JanitorEventRecord
from sqlbuild.executor.janitor_events.types import JanitorEventType
from tests.integration.src.sqlbuild.executor.janitor_events.main._test_types import (
    JanitorEventWriteTestCase,
)

ARCHIVE_NAME: str = "_SQB_ARCHIVE__20260924T101500Z__orders"


@pytest.mark.parametrize(
    "test_case",
    (
        JanitorEventWriteTestCase(
            description="repeated write of one deterministic event appends a single row",
            write_attempts=2,
            expected_row_count=1,
            expected_write_results=(True, False),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_repeated_janitor_event_when_writing_then_insert_is_idempotent(
    test_case: JanitorEventWriteTestCase,
    tmp_path: Path,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "janitor_events.duckdb")})
    archived_at: datetime = datetime(2026, 9, 24, 10, 15, 0, tzinfo=UTC)
    record: JanitorEventRecord = JanitorEventRecord(
        event_id=build_janitor_event_id(
            event_type=JanitorEventType.ARCHIVE,
            run_id="run_orders_cleanup",
            relation_database=None,
            relation_schema="main",
            archive_name=ARCHIVE_NAME,
        ),
        schema_version=JANITOR_EVENT_SCHEMA_VERSION,
        event_type=JanitorEventType.ARCHIVE,
        occurred_at=archived_at,
        run_id="run_orders_cleanup",
        relation_database=None,
        relation_schema="main",
        relation_type="BASE TABLE",
        original_name="orders",
        original_qualified_name="main.orders",
        archive_name=ARCHIVE_NAME,
        archive_qualified_name=f"main.{ARCHIVE_NAME}",
        archived_at=archived_at,
    )
    try:
        adapter.execute(
            connection=connection,
            sql=adapter.render_create_janitor_event_table_sql(database=None, schema="main"),
        )
        write_results: tuple[bool, ...] = tuple(
            write_janitor_event_record(
                connection=connection,
                execute=adapter.execute,
                record=record,
                render_qualified_name=adapter.render_qualified_name,
            )
            for _ in range(test_case.write_attempts)
        )
        rows: list[tuple[object, ...]] = connection.execute(
            f"SELECT {', '.join(JANITOR_EVENT_COLUMNS)} FROM main._sqlbuild_janitor_events"
        ).fetchall()
    finally:
        adapter.close(connection)

    assert write_results == test_case.expected_write_results
    assert len(rows) == test_case.expected_row_count
    assert rows[0] == (
        record.event_id,
        JANITOR_EVENT_SCHEMA_VERSION,
        "archive",
        archived_at.replace(tzinfo=None),
        "run_orders_cleanup",
        None,
        "main",
        "BASE TABLE",
        "orders",
        "main.orders",
        ARCHIVE_NAME,
        f"main.{ARCHIVE_NAME}",
        archived_at.replace(tzinfo=None),
    )
