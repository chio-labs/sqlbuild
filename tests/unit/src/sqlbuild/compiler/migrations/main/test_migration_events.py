"""Unit coverage for append-only migration event projection and storage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import duckdb
import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.migrations.main._newest_event import newest_migration_event_mentioning
from sqlbuild.compiler.migrations.main._read_events import read_migration_events
from sqlbuild.compiler.migrations.main.deterministic_event_id import (
    deterministic_migration_event_id,
)
from sqlbuild.compiler.migrations.main.write_event import write_migration_event
from sqlbuild.compiler.migrations.models import MigrationEvent, MigrationRelation
from sqlbuild.compiler.migrations.types import MigrationDecision, MigrationDiscovery
from tests.unit.src.sqlbuild.compiler.migrations.main._test_types import NewestEventTestCase

_STARTED_AT: datetime = datetime(2026, 1, 1, tzinfo=UTC)


def _relation(name: str) -> MigrationRelation:
    return MigrationRelation(database=None, schema="main", name=name)


def _event(*, origin: str, destination: str, day: int) -> MigrationEvent:
    return MigrationEvent(
        event_id=deterministic_migration_event_id(
            run_id=f"run-{day}",
            target_name="dev",
            origin=_relation(origin),
            destination=_relation(destination),
        ),
        target_name="dev",
        origin_model=origin,
        origin=_relation(origin),
        destination_model=destination,
        destination=_relation(destination),
        origin_version_hash=f"hash-{origin}",
        discovery=MigrationDiscovery.MANUAL,
        decision=MigrationDecision.MIGRATE,
        run_id=f"run-{day}",
        created_at=_STARTED_AT + timedelta(days=day),
    )


@pytest.mark.parametrize(
    "test_case",
    [
        NewestEventTestCase(
            description="day nine destination sees the day five event as origin",
            events=(("stg_orders", "stg_customer_orders"), ("stg_customer_orders", "stg_orders")),
            relation="stg_customer_orders",
            expected=("stg_customer_orders", "stg_orders"),
        ),
        NewestEventTestCase(
            description="day five destination sees the day one event as origin",
            events=(("stg_orders", "stg_customer_orders"),),
            relation="stg_orders",
            expected=("stg_orders", "stg_customer_orders"),
        ),
        NewestEventTestCase(
            description="unrelated relation has no event",
            events=(("stg_orders", "stg_customer_orders"),),
            relation="dim_customers",
            expected=None,
        ),
        NewestEventTestCase(
            description="relation identity is case insensitive",
            events=(("STG_ORDERS", "Stg_Customer_Orders"),),
            relation="stg_customer_orders",
            expected=("STG_ORDERS", "Stg_Customer_Orders"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_event_history_when_projecting_newest_mention_then_returns_latest_event(
    test_case: NewestEventTestCase,
) -> None:
    events: tuple[MigrationEvent, ...] = tuple(
        _event(origin=origin, destination=destination, day=index * 4 + 1)
        for index, (origin, destination) in enumerate(test_case.events)
    )

    newest: MigrationEvent | None = newest_migration_event_mentioning(
        events=reversed(events), relation=_relation(test_case.relation)
    )

    projected: tuple[str, str] | None = (
        None if newest is None else (newest.origin.name, newest.destination.name)
    )
    assert projected == test_case.expected


def test_given_repeated_event_write_when_reading_then_event_is_stored_once() -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    event: MigrationEvent = _event(origin="stg_orders", destination="stg_customer_orders", day=1)

    for _ in range(2):
        write_migration_event(
            connection=connection,
            execute=adapter.execute,
            event=event,
            render_qualified_name=adapter.render_qualified_name,
            render_framework_type=adapter.render_framework_type,
            transient=False,
        )
    stored: tuple[MigrationEvent, ...] = read_migration_events(
        connection=connection,
        execute=adapter.execute,
        database=None,
        schema="main",
        render_qualified_name=adapter.render_qualified_name,
    )

    assert stored == (event,)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
