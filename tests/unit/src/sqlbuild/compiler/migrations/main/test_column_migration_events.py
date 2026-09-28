"""Unit coverage for append-only column migration event storage and projection."""

from __future__ import annotations

import duckdb
import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.migrations.main._newest_column_event import (
    newest_column_migration_event_mentioning,
)
from sqlbuild.compiler.migrations.main._read_column_events import read_column_migration_events
from sqlbuild.compiler.migrations.main.write_column_event import write_column_migration_event
from sqlbuild.compiler.migrations.models import ColumnMigrationEvent
from tests.unit.src.sqlbuild.compiler.migrations.main._test_types import (
    ColumnEventStorageTestCase,
    NewestColumnEventTestCase,
)
from tests.unit.src.sqlbuild.compiler.migrations.main.helpers import (
    column_migration_event,
    main_relation,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ColumnEventStorageTestCase(
            description="writing the same event twice stores it once",
            write_count=2,
            foreign_decisions=(),
            expected_stored_count=1,
        ),
        ColumnEventStorageTestCase(
            description="rows with a decision from a newer version are skipped",
            write_count=1,
            foreign_decisions=("renamed_by_a_future_version",),
            expected_stored_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_column_events_when_writing_and_reading_then_rows_are_idempotent(
    test_case: ColumnEventStorageTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    event: ColumnMigrationEvent = column_migration_event(
        origin="amount", destination="revenue", day=1
    )

    for _ in range(test_case.write_count):
        write_column_migration_event(
            connection=connection,
            execute=adapter.execute,
            event=event,
            render_qualified_name=adapter.render_qualified_name,
            create_table_sql=adapter.render_create_column_migration_state_table_sql(
                database=None, schema="main"
            ),
        )
    for foreign_decision in test_case.foreign_decisions:
        _ = connection.execute(
            "INSERT INTO main._sqlbuild_column_migrations (event_id, model_name, relation_name, "
            "origin_column, destination_column, discovery, decision, run_id, created_at) VALUES "
            f"('future', 'fct_orders', 'fct_orders', 'tax', 'levy', 'manual', "
            f"'{foreign_decision}', 'run-9', TIMESTAMP '2026-01-09')"
        )
    stored: tuple[ColumnMigrationEvent, ...] = read_column_migration_events(
        connection=connection,
        execute=adapter.execute,
        database=None,
        schema="main",
        render_qualified_name=adapter.render_qualified_name,
    )

    assert len(stored) == test_case.expected_stored_count
    assert stored == (event,)


@pytest.mark.parametrize(
    "test_case",
    [
        NewestColumnEventTestCase(
            description="latest rename of either column wins",
            renames=(("amount", "revenue"), ("revenue", "amount")),
            origin_column="amount",
            destination_column="revenue",
            expected_newest_index=1,
        ),
        NewestColumnEventTestCase(
            description="column names are case insensitive",
            renames=(("AMOUNT", "Revenue"),),
            origin_column="amount",
            destination_column="revenue",
            expected_newest_index=0,
        ),
        NewestColumnEventTestCase(
            description="unrelated columns have no event",
            renames=(("tax", "levy"),),
            origin_column="amount",
            destination_column="revenue",
            expected_newest_index=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_column_event_history_when_projecting_newest_mention_then_returns_latest_event(
    test_case: NewestColumnEventTestCase,
) -> None:
    events: tuple[ColumnMigrationEvent, ...] = tuple(
        column_migration_event(origin=origin, destination=destination, day=index + 1)
        for index, (origin, destination) in enumerate(test_case.renames)
    )
    events_by_index: dict[int | None, ColumnMigrationEvent] = dict(enumerate(events))

    newest: ColumnMigrationEvent | None = newest_column_migration_event_mentioning(
        events=reversed(events),
        relation=main_relation("fct_orders"),
        origin_column=test_case.origin_column,
        destination_column=test_case.destination_column,
    )

    assert newest == events_by_index.get(test_case.expected_newest_index)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
