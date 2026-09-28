"""Fixtures for executor column rename helpers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import duckdb

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.migrations.main.deterministic_column_event_id import (
    deterministic_column_migration_event_id,
)
from sqlbuild.compiler.migrations.models import ColumnMigrationEvent, MigrationRelation
from sqlbuild.compiler.migrations.types import ColumnMigrationDecision, MigrationDiscovery
from sqlbuild.compiler.planner.models import ColumnMigrationPlanEntry

RELATION: str = "main.fct_orders"


def orders_connection() -> duckdb.DuckDBPyConnection:
    """Return an in-memory warehouse holding one orders table with amount and tax."""

    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    _ = connection.execute(
        f"CREATE TABLE {RELATION} AS SELECT 1 AS order_id, 101 AS amount, 7 AS tax"
    )
    return connection


def pending_rename(*, origin_column: str, destination_column: str) -> ColumnMigrationPlanEntry:
    """Return one planned in-place rename on the orders table."""

    return ColumnMigrationPlanEntry(
        model_name="fct_orders",
        destination=CompiledRelationLocation(
            database=None, schema="main", name="fct_orders", qualified_name=RELATION
        ),
        origin_column=origin_column,
        destination_column=destination_column,
        discovery=MigrationDiscovery.MANUAL,
        decision=ColumnMigrationDecision.RENAME,
        target_name="dev",
    )


def rename_then_overlap(
    *, adapter: DuckDbAdapter, connection: duckdb.DuckDBPyConnection
) -> Callable[..., None]:
    """Return a rename that lets an overlapping build rename tax to levy right after it."""

    original: Callable[..., None] = adapter.rename_column

    def rename(**kwargs: Any) -> None:
        original(**kwargs)
        _ = connection.execute(f"ALTER TABLE {RELATION} RENAME COLUMN tax TO levy")

    return rename


def live_column_names(connection: duckdb.DuckDBPyConnection) -> tuple[str, ...]:
    """Return the orders table's physical column names in order."""

    return tuple(
        str(row[0])
        for row in connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'fct_orders' ORDER BY ordinal_position"
        ).fetchall()
    )


_RENAMES_STARTED_AT: datetime = datetime(2026, 1, 1, tzinfo=UTC)
_RENAMED_RELATION: MigrationRelation = MigrationRelation(
    database=None, schema="analytics", name="daily_revenue"
)


def column_rename(*, origin: str, destination: str, day: int) -> ColumnMigrationEvent:
    """Return one manual column rename on analytics.daily_revenue."""

    return ColumnMigrationEvent(
        event_id=deterministic_column_migration_event_id(
            run_id=f"run-{day}",
            target_name=None,
            relation=_RENAMED_RELATION,
            origin_column=origin,
            destination_column=destination,
        ),
        target_name=None,
        model_name="daily_revenue",
        relation=_RENAMED_RELATION,
        origin_column=origin,
        destination_column=destination,
        discovery=MigrationDiscovery.MANUAL,
        decision=ColumnMigrationDecision.RENAME,
        run_id=f"run-{day}",
        created_at=_RENAMES_STARTED_AT + timedelta(days=day),
    )


def snowflake_location(*, adapter: SnowflakeAdapter, name: str) -> CompiledRelationLocation:
    """Return an analytics relation rendered the way Snowflake qualifies it."""

    return CompiledRelationLocation(
        database=None,
        schema="analytics",
        name=name,
        qualified_name=adapter.render_qualified_name(database=None, schema="analytics", name=name),
    )
