from __future__ import annotations

import pytest

from sqlbuild.archives._helpers.sql import (
    build_create_table_sql,
    build_insert_sql,
    build_read_target_sql,
)
from sqlbuild.archives.models import ArchiveEvent
from sqlbuild.archives.types import ArchiveRecordType
from tests.unit.src.sqlbuild.archives._test_types import (
    ArchiveRenderedSqlTestCase,
    ArchiveSqlTestCase,
)
from tests.unit.src.sqlbuild.archives.helpers import archive_event, framework_type, qualified_name


@pytest.mark.parametrize(
    "test_case",
    [
        ArchiveSqlTestCase(
            description="portable table is permanent and append only",
            expected_fragments=(
                "CREATE TABLE IF NOT EXISTS warehouse.analytics._sqlbuild_archive_events",
                "event_id TEXT",
                "retention_days BIGINT",
                "created_at TIMESTAMP",
            ),
            unexpected_fragments=("TRANSIENT", "CREATE OR REPLACE", "lifecycle_status"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_archive_state_when_rendering_table_then_uses_append_only_schema(
    test_case: ArchiveSqlTestCase,
) -> None:
    sql: str = build_create_table_sql(
        database="warehouse",
        schema="analytics",
        render_qualified_name=qualified_name,
        render_framework_type=framework_type,
    )
    assert all(fragment in sql for fragment in test_case.expected_fragments)
    assert all(fragment not in sql for fragment in test_case.unexpected_fragments)


@pytest.mark.parametrize(
    "test_case",
    [
        ArchiveRenderedSqlTestCase(
            description="idempotent archive event insert",
            expected_fragments=("WHERE NOT EXISTS", "WHERE event_id = 'event-1'"),
            unexpected_fragments=("UPDATE",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_archive_event_when_rendering_insert_then_guards_deterministic_event_id(
    test_case: ArchiveRenderedSqlTestCase,
) -> None:
    event: ArchiveEvent = archive_event(
        event_id="event-1", record_type=ArchiveRecordType.REQUIREMENT
    )
    sql: str = build_insert_sql(event=event, render_qualified_name=qualified_name)
    assert all(fragment in sql for fragment in test_case.expected_fragments)
    assert all(fragment not in sql for fragment in test_case.unexpected_fragments)


@pytest.mark.parametrize(
    "test_case",
    [
        ArchiveRenderedSqlTestCase(
            description="bounded target history read",
            expected_fragments=(
                "target_database = 'warehouse'",
                "target_schema = 'analytics'",
                "target_name = 'orders'",
                "ORDER BY created_at, event_id",
            ),
            unexpected_fragments=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_target_when_rendering_history_read_then_orders_events_stably(
    test_case: ArchiveRenderedSqlTestCase,
) -> None:
    sql: str = build_read_target_sql(
        database="warehouse",
        schema="analytics",
        target_name="orders",
        render_qualified_name=qualified_name,
    )
    assert all(fragment in sql for fragment in test_case.expected_fragments)
    assert all(fragment not in sql for fragment in test_case.unexpected_fragments)
