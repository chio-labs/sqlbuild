"""Unit coverage for append-only migration event projection and storage."""

from __future__ import annotations

import duckdb
import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.migrations.main._newest_event import newest_migration_event_mentioning
from sqlbuild.compiler.migrations.main._read_events import read_migration_events
from sqlbuild.compiler.migrations.main.write_event import write_migration_event
from sqlbuild.compiler.migrations.models import MigrationEvent
from tests.unit.src.sqlbuild.compiler.migrations.main._test_types import (
    NewestEventTestCase,
    RepeatedEventWriteTestCase,
)
from tests.unit.src.sqlbuild.compiler.migrations.main.helpers import (
    main_relation,
    migration_event,
)


@pytest.mark.parametrize(
    "test_case",
    [
        NewestEventTestCase(
            description="day nine destination sees the day five event as origin",
            events=(("stg_orders", "stg_customer_orders"), ("stg_customer_orders", "stg_orders")),
            relation="stg_customer_orders",
            expected_newest_index=1,
        ),
        NewestEventTestCase(
            description="day five destination sees the day one event as origin",
            events=(("stg_orders", "stg_customer_orders"),),
            relation="stg_orders",
            expected_newest_index=0,
        ),
        NewestEventTestCase(
            description="unrelated relation has no event",
            events=(("stg_orders", "stg_customer_orders"),),
            relation="dim_customers",
            expected_newest_index=None,
        ),
        NewestEventTestCase(
            description="relation identity is case insensitive",
            events=(("STG_ORDERS", "Stg_Customer_Orders"),),
            relation="stg_customer_orders",
            expected_newest_index=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_event_history_when_projecting_newest_mention_then_returns_latest_event(
    test_case: NewestEventTestCase,
) -> None:
    events: tuple[MigrationEvent, ...] = tuple(
        migration_event(origin=origin, destination=destination, day=index * 4 + 1)
        for index, (origin, destination) in enumerate(test_case.events)
    )
    events_by_index: dict[int | None, MigrationEvent] = dict(enumerate(events))

    newest: MigrationEvent | None = newest_migration_event_mentioning(
        events=reversed(events), relation=main_relation(test_case.relation)
    )

    assert newest == events_by_index.get(test_case.expected_newest_index)


@pytest.mark.parametrize(
    "test_case",
    [
        RepeatedEventWriteTestCase(
            description="writing the same event twice stores it once",
            write_count=2,
            expected_stored_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_repeated_event_write_when_reading_then_event_is_stored_once(
    test_case: RepeatedEventWriteTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    event: MigrationEvent = migration_event(
        origin="stg_orders", destination="stg_customer_orders", day=1
    )

    for _ in range(test_case.write_count):
        write_migration_event(
            connection=connection,
            execute=adapter.execute,
            event=event,
            render_qualified_name=adapter.render_qualified_name,
            create_table_sql=adapter.render_create_migration_state_table_sql(
                database=None, schema="main"
            ),
        )
    stored: tuple[MigrationEvent, ...] = read_migration_events(
        connection=connection,
        execute=adapter.execute,
        database=None,
        schema="main",
        render_qualified_name=adapter.render_qualified_name,
    )

    assert len(stored) == test_case.expected_stored_count
    assert stored == (event,)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
