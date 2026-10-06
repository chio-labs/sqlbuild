"""Unit coverage for per-adapter in-place column rename SQL and column migration state."""

from __future__ import annotations

import pytest

from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.motherduck.classes.motherduck_adapter import MotherDuckAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from tests.unit.src.sqlbuild.adapters._test_types import (
    AdapterColumnMigrationStateTableTestCase,
    AdapterRenameColumnSqlTestCase,
    DatabricksColumnMappingTestCase,
)
from tests.unit.src.sqlbuild.adapters.helpers import recording_execute

_DATABRICKS_TABLE: str = "`main`.`analytics`.`fct_orders`"


@pytest.mark.parametrize(
    "test_case",
    [
        AdapterRenameColumnSqlTestCase(
            description="duckdb renames in place",
            adapter=DuckDbAdapter(),
            destination="main.fct_orders",
            old_name="amount",
            new_name="revenue",
            expected_statements=(
                'ALTER TABLE main.fct_orders RENAME COLUMN "amount" TO "revenue"',
            ),
        ),
        AdapterRenameColumnSqlTestCase(
            description="motherduck renames in place",
            adapter=MotherDuckAdapter(),
            destination="orders.main.fct_orders",
            old_name="amount",
            new_name="revenue",
            expected_statements=(
                'ALTER TABLE orders.main.fct_orders RENAME COLUMN "amount" TO "revenue"',
            ),
        ),
        AdapterRenameColumnSqlTestCase(
            description="postgres folds the unquoted new name to lower case",
            adapter=PostgresAdapter(),
            destination='"analytics"."fct_orders"',
            old_name="amount",
            new_name="Revenue",
            expected_statements=(
                'ALTER TABLE "analytics"."fct_orders" RENAME COLUMN "amount" TO "revenue"',
            ),
        ),
        AdapterRenameColumnSqlTestCase(
            description="snowflake keeps the physical old name and upper-cases the new name",
            adapter=SnowflakeAdapter(),
            destination="ANALYTICS.PUBLIC.FCT_ORDERS",
            old_name="AMOUNT",
            new_name="revenue",
            expected_statements=(
                'ALTER TABLE ANALYTICS.PUBLIC.FCT_ORDERS RENAME COLUMN "AMOUNT" TO "REVENUE"',
            ),
        ),
        AdapterRenameColumnSqlTestCase(
            description="bigquery renames with backtick identifiers",
            adapter=BigQueryAdapter(),
            destination="`orders-project`.`analytics`.`fct_orders`",
            old_name="amount",
            new_name="revenue",
            expected_statements=(
                "ALTER TABLE `orders-project`.`analytics`.`fct_orders` "
                "RENAME COLUMN `amount` TO `revenue`",
            ),
        ),
        AdapterRenameColumnSqlTestCase(
            description="databricks renames with backtick identifiers",
            adapter=DatabricksAdapter(),
            destination="`main`.`analytics`.`fct_orders`",
            old_name="amount",
            new_name="revenue",
            expected_statements=(
                "ALTER TABLE `main`.`analytics`.`fct_orders` RENAME COLUMN `amount` TO `revenue`",
            ),
        ),
        AdapterRenameColumnSqlTestCase(
            description="sql server renames through sp_rename",
            adapter=SqlServerAdapter(),
            destination="[orders].[analytics].[fct_orders]",
            old_name="amount",
            new_name="revenue",
            expected_statements=(
                "EXEC sp_rename N'[analytics].[fct_orders].[amount]', N'revenue', 'COLUMN'",
            ),
        ),
        AdapterRenameColumnSqlTestCase(
            description="sql server escapes quotes in both names",
            adapter=SqlServerAdapter(),
            destination="[analytics].[fct_orders]",
            old_name="o'amount",
            new_name="o'revenue",
            expected_statements=(
                "EXEC sp_rename N'[analytics].[fct_orders].[o''amount]', N'o''revenue', 'COLUMN'",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_when_rendering_column_rename_then_uses_the_engine_statement(
    test_case: AdapterRenameColumnSqlTestCase,
) -> None:
    statements: tuple[str, ...] = test_case.adapter.render_rename_column(
        destination=test_case.destination,
        old_name=test_case.old_name,
        new_name=test_case.new_name,
    )

    assert statements == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        AdapterColumnMigrationStateTableTestCase(
            description="duckdb creates the column migration table when missing",
            adapter=DuckDbAdapter(),
            expected_fragments=(
                "CREATE TABLE IF NOT EXISTS main._sqlbuild_column_migrations",
                "origin_column",
                "destination_column",
            ),
        ),
        AdapterColumnMigrationStateTableTestCase(
            description="snowflake state tables are permanent with maximum time travel",
            adapter=SnowflakeAdapter(),
            expected_fragments=(
                "CREATE TABLE IF NOT EXISTS main._sqlbuild_column_migrations",
                "origin_column",
                ") DATA_RETENTION_TIME_IN_DAYS = 90",
            ),
        ),
        AdapterColumnMigrationStateTableTestCase(
            description="sql server guards the create with an existence check",
            adapter=SqlServerAdapter(),
            expected_fragments=(
                "IF NOT EXISTS (SELECT 1 FROM information_schema.tables",
                "table_name = '_sqlbuild_column_migrations'",
                "CREATE TABLE main._sqlbuild_column_migrations (",
                "created_at DATETIME2",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_when_rendering_column_migration_state_table_then_ddl_is_adapter_native(
    test_case: AdapterColumnMigrationStateTableTestCase,
) -> None:
    sql: str = test_case.adapter.render_create_column_migration_state_table_sql(
        database=None, schema="main"
    )

    assert all(fragment in sql for fragment in test_case.expected_fragments), sql


@pytest.mark.parametrize(
    "test_case",
    [
        DatabricksColumnMappingTestCase(
            description="name column mapping allows renames",
            property_rows=[("delta.columnMapping.mode", "name")],
            expected_available=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_databricks_column_mapping_when_renaming_then_renames_in_place(
    test_case: DatabricksColumnMappingTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter: DatabricksAdapter = DatabricksAdapter()
    executed: list[str] = []
    monkeypatch.setattr(
        adapter, "execute", recording_execute(rows=test_case.property_rows, executed=executed)
    )

    reason: str | None = adapter.column_rename_unavailable_reason(
        connection=None, destination=_DATABRICKS_TABLE
    )
    adapter.rename_column(
        connection=None,
        destination=_DATABRICKS_TABLE,
        old_name="amount",
        new_name="revenue",
        statement_recorder=StatementRecorder(),
    )

    assert (reason is None) is test_case.expected_available
    assert executed[-1] == f"ALTER TABLE {_DATABRICKS_TABLE} RENAME COLUMN `amount` TO `revenue`"


@pytest.mark.parametrize(
    "test_case",
    [
        DatabricksColumnMappingTestCase(
            description="missing column mapping refuses renames",
            property_rows=[
                (
                    "delta.columnMapping.mode",
                    "Table main.analytics.fct_orders does not have property: "
                    "delta.columnMapping.mode",
                )
            ],
            expected_available=False,
        ),
        DatabricksColumnMappingTestCase(
            description="id column mapping refuses renames",
            property_rows=[("delta.columnMapping.mode", "id")],
            expected_available=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_databricks_without_name_mapping_when_renaming_then_fails_before_altering(
    test_case: DatabricksColumnMappingTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter: DatabricksAdapter = DatabricksAdapter()
    executed: list[str] = []
    monkeypatch.setattr(
        adapter, "execute", recording_execute(rows=test_case.property_rows, executed=executed)
    )

    reason: str | None = adapter.column_rename_unavailable_reason(
        connection=None, destination=_DATABRICKS_TABLE
    )
    with pytest.raises(AdapterUserError, match="delta.columnMapping.mode"):
        adapter.rename_column(
            connection=None,
            destination=_DATABRICKS_TABLE,
            old_name="amount",
            new_name="revenue",
            statement_recorder=StatementRecorder(),
        )

    assert (reason is None) is test_case.expected_available
    assert reason is not None
    assert "SET TBLPROPERTIES ('delta.columnMapping.mode' = 'name'" in reason
    assert all("RENAME COLUMN" not in sql for sql in executed)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
