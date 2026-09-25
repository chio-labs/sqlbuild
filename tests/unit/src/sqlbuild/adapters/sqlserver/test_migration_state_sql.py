"""SQL Server rendering coverage for the append-only model migration state table."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from sqlbuild.compiler.migrations.main._read_events import read_migration_events
from sqlbuild.compiler.migrations.main.write_event import write_migration_event
from sqlbuild.compiler.migrations.models import MigrationEvent, MigrationRelation
from sqlbuild.compiler.migrations.types import MigrationDecision, MigrationDiscovery
from tests.unit.src.sqlbuild.adapters.sqlserver._test_types import (
    SqlServerMigrationEventReadTestCase,
    SqlServerMigrationEventWriteTestCase,
    SqlServerMigrationTableTestCase,
)
from tests.unit.src.sqlbuild.adapters.sqlserver.helpers import ScriptedSqlServerConnection

_CREATED_AT: datetime = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
_EVENT: MigrationEvent = MigrationEvent(
    event_id="event-1",
    target_name="dev",
    origin_model="stg_orders",
    origin=MigrationRelation(database=None, schema="dbo", name="stg_orders"),
    destination_model="stg_customer_orders",
    destination=MigrationRelation(database=None, schema="dbo", name="stg_customer_orders"),
    origin_version_hash="hash-1",
    discovery=MigrationDiscovery.MANUAL,
    decision=MigrationDecision.MIGRATE,
    run_id="run-1",
    created_at=_CREATED_AT,
)
_GUARDED_CREATE: str = (
    "IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'dbo' "
    "AND table_name = '_sqlbuild_migrations') CREATE TABLE dbo._sqlbuild_migrations ("
)
_EXISTING: str = "SELECT event_id FROM dbo._sqlbuild_migrations WHERE event_id = 'event-1'"
_INSERT: str = "INSERT INTO dbo._sqlbuild_migrations (event_id, target_name"


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerMigrationTableTestCase(
            description="state table creation is guarded by a catalog check",
            schema="dbo",
            expected_prefix=_GUARDED_CREATE,
            expected_suffix="run_id NVARCHAR(MAX), created_at DATETIME2)",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sqlserver_when_rendering_migration_table_then_uses_guarded_create(
    test_case: SqlServerMigrationTableTestCase,
) -> None:
    """SQL Server has no CREATE TABLE IF NOT EXISTS, so creation is guarded by a catalog check."""

    sql: str = SqlServerAdapter().render_create_migration_state_table_sql(
        database=None, schema=test_case.schema
    )

    assert sql.startswith(test_case.expected_prefix)
    assert "IF NOT EXISTS dbo" not in sql
    assert sql.endswith(test_case.expected_suffix)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerMigrationEventWriteTestCase(
            description="new event is checked then inserted with values",
            existing_rows=(),
            expected_statement_prefixes=(_GUARDED_CREATE, _EXISTING, _INSERT),
        ),
        SqlServerMigrationEventWriteTestCase(
            description="already recorded event is not inserted again",
            existing_rows=(("event-1",),),
            expected_statement_prefixes=(_GUARDED_CREATE, _EXISTING),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sqlserver_when_writing_migration_event_then_statements_are_tsql(
    test_case: SqlServerMigrationEventWriteTestCase,
) -> None:
    """Event writes avoid SELECT-without-FROM guards and ANSI TIMESTAMP casts."""

    adapter: SqlServerAdapter = SqlServerAdapter()
    connection: ScriptedSqlServerConnection = ScriptedSqlServerConnection(
        rows=test_case.existing_rows
    )

    write_migration_event(
        connection=connection,
        execute=adapter.execute,
        event=_EVENT,
        render_qualified_name=adapter.render_qualified_name,
        create_table_sql=adapter.render_create_migration_state_table_sql(
            database=None, schema="dbo"
        ),
    )

    assert tuple(
        sql[: len(prefix)]
        for sql, prefix in zip(
            connection.executed_sql, test_case.expected_statement_prefixes, strict=True
        )
    ) == (test_case.expected_statement_prefixes)
    assert all("AS TIMESTAMP" not in sql for sql in connection.executed_sql)
    assert all("NOT EXISTS (SELECT 1 FROM dbo." not in sql for sql in connection.executed_sql)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerMigrationEventReadTestCase(
            description="naive datetime2 values decode as utc",
            stored_created_at=datetime(2026, 1, 2, 3, 4, 5),
            expected_read_suffix="FROM dbo._sqlbuild_migrations ORDER BY created_at, event_id",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sqlserver_datetime2_rows_when_reading_events_then_decodes_utc_events(
    test_case: SqlServerMigrationEventReadTestCase,
) -> None:
    """Reads use plain ORDER BY and decode naive DATETIME2 values as UTC."""

    adapter: SqlServerAdapter = SqlServerAdapter()
    connection: ScriptedSqlServerConnection = ScriptedSqlServerConnection(
        rows=(
            (
                "event-1",
                "dev",
                "stg_orders",
                None,
                "dbo",
                "stg_orders",
                "stg_customer_orders",
                None,
                "dbo",
                "stg_customer_orders",
                "hash-1",
                "manual",
                "migrate",
                "run-1",
                test_case.stored_created_at,
            ),
        )
    )

    events: tuple[MigrationEvent, ...] = read_migration_events(
        connection=connection,
        execute=adapter.execute,
        database=None,
        schema="dbo",
        render_qualified_name=adapter.render_qualified_name,
    )

    assert events == (_EVENT,)
    assert connection.executed_sql[0].endswith(test_case.expected_read_suffix)
    assert "LIMIT" not in connection.executed_sql[0]


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
