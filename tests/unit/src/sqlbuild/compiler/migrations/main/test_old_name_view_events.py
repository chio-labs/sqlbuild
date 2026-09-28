"""Unit coverage for append-only old-name view facts and their projection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.migrations.main._project_old_name_views import project_old_name_views
from sqlbuild.compiler.migrations.main.read_old_name_view_events import (
    read_old_name_view_events,
)
from sqlbuild.compiler.migrations.main.write_old_name_view_event import write_old_name_view_event
from sqlbuild.compiler.migrations.models import (
    MigrationEvent,
    OldNameViewEvent,
    OldNameViewHistory,
)
from sqlbuild.compiler.migrations.types import OldNameViewEventType
from tests.unit.src.sqlbuild.compiler.migrations.main._test_types import (
    OldNameViewProjectionTestCase,
    OldNameViewStorageTestCase,
)
from tests.unit.src.sqlbuild.compiler.migrations.main.helpers import (
    migration_event,
    old_name_fact,
)

_NOW: datetime = datetime(2026, 2, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    "test_case",
    [
        OldNameViewStorageTestCase(
            description="writing the same fact twice stores it once",
            write_count=2,
            foreign_event_types=(),
            expected_event_types=("view_created",),
        ),
        OldNameViewStorageTestCase(
            description="facts of a type from a newer version are skipped",
            write_count=1,
            foreign_event_types=("view_renamed_by_a_future_version",),
            expected_event_types=("view_created",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_old_name_facts_when_writing_and_reading_then_rows_are_idempotent(
    test_case: OldNameViewStorageTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    move: MigrationEvent = migration_event(origin="revenue", destination="daily_revenue", day=1)
    fact: OldNameViewEvent = old_name_fact(
        move=move,
        event_type=OldNameViewEventType.VIEW_CREATED,
        expires_at=_NOW,
        column_aliases=(("amount", "revenue"),),
    )

    for _ in range(test_case.write_count):
        write_old_name_view_event(
            connection=connection,
            execute=adapter.execute,
            event=fact,
            render_qualified_name=adapter.render_qualified_name,
            create_table_sql=adapter.render_create_old_name_view_state_table_sql(
                database=None, schema="main"
            ),
        )
    for foreign in test_case.foreign_event_types:
        _ = connection.execute(
            "INSERT INTO main._sqlbuild_old_name_views (event_id, event_type, "
            "migration_event_id, destination_model, old_name, new_name, run_id, created_at) "
            f"VALUES ('future', '{foreign}', 'm', 'daily_revenue', 'revenue', 'daily_revenue', "
            "'run-9', TIMESTAMP '2026-01-09')"
        )
    stored: tuple[OldNameViewEvent, ...] = read_old_name_view_events(
        connection=connection,
        execute=adapter.execute,
        database=None,
        schema="main",
        render_qualified_name=adapter.render_qualified_name,
    )

    assert tuple(event.event_type.value for event in stored) == test_case.expected_event_types
    assert stored == (fact,)


@pytest.mark.parametrize(
    "test_case",
    [
        OldNameViewProjectionTestCase(
            description="move recorded before old-name views existed has no history",
            recorded_types=(),
            recorded_moves=1,
            expires_in_days=1,
            expected_statuses=(),
        ),
        OldNameViewProjectionTestCase(
            description="requirement without its move is ignored",
            recorded_types=("required",),
            recorded_moves=0,
            expires_in_days=1,
            expected_statuses=(),
        ),
        OldNameViewProjectionTestCase(
            description="required move waits for its archive",
            recorded_types=("required",),
            recorded_moves=1,
            expires_in_days=1,
            expected_statuses=("pending_archive",),
        ),
        OldNameViewProjectionTestCase(
            description="archived move waits for its view",
            recorded_types=("required", "origin_archived"),
            recorded_moves=1,
            expires_in_days=1,
            expected_statuses=("pending_view",),
        ),
        OldNameViewProjectionTestCase(
            description="created view is live until it expires",
            recorded_types=("required", "origin_archived", "view_created"),
            recorded_moves=1,
            expires_in_days=1,
            expected_statuses=("live",),
        ),
        OldNameViewProjectionTestCase(
            description="created view past its expiry is expired",
            recorded_types=("required", "origin_archived", "view_created"),
            recorded_moves=1,
            expires_in_days=-1,
            expected_statuses=("expired",),
        ),
        OldNameViewProjectionTestCase(
            description="dropped view is dropped",
            recorded_types=("required", "origin_archived", "view_created", "view_dropped"),
            recorded_moves=1,
            expires_in_days=-1,
            expected_statuses=("dropped",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_recorded_facts_when_projecting_then_status_follows_the_newest_step(
    test_case: OldNameViewProjectionTestCase,
) -> None:
    move: MigrationEvent = migration_event(origin="revenue", destination="daily_revenue", day=1)
    facts: tuple[OldNameViewEvent, ...] = tuple(
        old_name_fact(
            move=move,
            event_type=OldNameViewEventType(event_type),
            expires_at=_NOW + timedelta(days=test_case.expires_in_days),
        )
        for event_type in test_case.recorded_types
    )

    histories: tuple[OldNameViewHistory, ...] = project_old_name_views(
        moves=(move,)[: test_case.recorded_moves], facts=facts
    )

    assert tuple(history.status(now=_NOW).value for history in histories) == (
        test_case.expected_statuses
    )
