"""Unit coverage for compatibility view SQL and column alias composition."""

from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from sqlbuild.compiler.migrations.models import ColumnMigrationEvent
from sqlbuild.executor.migrations._helpers.old_name_views import (
    compose_column_aliases,
    render_old_name_view_select,
)
from sqlbuild.executor.migrations.models import OldNameViewSource
from tests.unit.src.sqlbuild.executor.migrations._helpers._test_types import (
    AdapterOldNameSqlTestCase,
    ComposeColumnAliasesTestCase,
)
from tests.unit.src.sqlbuild.executor.migrations._helpers.helpers import (
    adapter_location,
    column_rename,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ComposeColumnAliasesTestCase(
            description="one rename aliases the new column back",
            renames=(("amount", "revenue"),),
            expected_aliases=(("amount", "revenue"),),
        ),
        ComposeColumnAliasesTestCase(
            description="chained renames alias the first name to the latest",
            renames=(("amount", "revenue"), ("revenue", "net_revenue")),
            expected_aliases=(("amount", "net_revenue"),),
        ),
        ComposeColumnAliasesTestCase(
            description="a rename back to the original name needs no alias",
            renames=(("amount", "revenue"), ("revenue", "amount")),
            expected_aliases=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_recorded_column_renames_when_composing_then_old_names_map_to_current(
    test_case: ComposeColumnAliasesTestCase,
) -> None:
    events: tuple[ColumnMigrationEvent, ...] = tuple(
        column_rename(origin=origin, destination=destination, day=day)
        for day, (origin, destination) in enumerate(test_case.renames, start=1)
    )

    assert compose_column_aliases(events) == test_case.expected_aliases


@pytest.mark.parametrize(
    "test_case",
    [
        AdapterOldNameSqlTestCase(
            description="snowflake view without aliases selects every column",
            adapter=SnowflakeAdapter(),
            database=None,
            column_aliases=(),
            expected_statements=(
                "CREATE OR REPLACE VIEW analytics.revenue AS SELECT * FROM analytics.daily_revenue",
            ),
            expected_state_table_prefix="CREATE TRANSIENT TABLE IF NOT EXISTS",
            expected_transactional=False,
        ),
        AdapterOldNameSqlTestCase(
            description="snowflake aliased column keeps its exact name and exposes the old one",
            adapter=SnowflakeAdapter(),
            database=None,
            column_aliases=(("amount", "revenue"),),
            expected_statements=(
                "CREATE OR REPLACE VIEW analytics.revenue AS "
                'SELECT "ORDER_ID", "REVENUE" AS "AMOUNT" FROM analytics.daily_revenue',
            ),
            expected_state_table_prefix="CREATE TRANSIENT TABLE IF NOT EXISTS",
            expected_transactional=False,
        ),
        AdapterOldNameSqlTestCase(
            description="bigquery view reads the new table by name",
            adapter=BigQueryAdapter(),
            database="orders-project",
            column_aliases=(("amount", "revenue"),),
            expected_statements=(
                "CREATE OR REPLACE VIEW `orders-project.analytics.revenue` AS SELECT `ORDER_ID`, "
                "`REVENUE` AS `amount` FROM `orders-project.analytics.daily_revenue`",
            ),
            expected_state_table_prefix=(
                "CREATE TABLE IF NOT EXISTS `orders-project.analytics._sqlbuild_old_name_views`"
            ),
            expected_transactional=False,
        ),
        AdapterOldNameSqlTestCase(
            description="databricks view reads the new table by name",
            adapter=DatabricksAdapter(),
            database="main",
            column_aliases=(("amount", "revenue"),),
            expected_statements=(
                "CREATE OR REPLACE VIEW `main`.`analytics`.`revenue` AS SELECT `ORDER_ID`, "
                "`REVENUE` AS `amount` FROM `main`.`analytics`.`daily_revenue`",
            ),
            expected_state_table_prefix=(
                "CREATE TABLE IF NOT EXISTS `main`.`analytics`.`_sqlbuild_old_name_views`"
            ),
            expected_transactional=False,
        ),
        AdapterOldNameSqlTestCase(
            description="sql server re-creates the view inside a transaction",
            adapter=SqlServerAdapter(),
            database=None,
            column_aliases=(("amount", "revenue"),),
            expected_statements=(
                "DROP VIEW IF EXISTS analytics.revenue",
                "CREATE VIEW analytics.revenue AS SELECT [ORDER_ID], [REVENUE] AS [amount] "
                "FROM analytics.daily_revenue",
            ),
            expected_state_table_prefix="IF NOT EXISTS (SELECT 1 FROM information_schema.tables",
            expected_transactional=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_compatibility_view_when_rendering_then_sql_reads_new_relation_by_name(
    test_case: AdapterOldNameSqlTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter: BaseAdapter = test_case.adapter

    def columns(**_: Any) -> tuple[ColumnInfo, ...]:
        return (
            ColumnInfo(name="ORDER_ID", type="NUMBER"),
            ColumnInfo(name="REVENUE", type="NUMBER"),
        )

    monkeypatch.setattr(adapter, "get_columns", columns)
    source: OldNameViewSource = OldNameViewSource(
        old=adapter_location(adapter=adapter, database=test_case.database, name="revenue"),
        new=adapter_location(adapter=adapter, database=test_case.database, name="daily_revenue"),
        column_aliases=test_case.column_aliases,
    )

    select_sql: str = render_old_name_view_select(adapter=adapter, connection=None, source=source)
    statements: tuple[str, ...] = adapter.render_create_view_as(
        destination=source.old.qualified_name or "", sql=select_sql
    )

    assert statements == test_case.expected_statements
    assert not adapter.views_bind_to_relation_identity()
    assert adapter.supports_transactional_ddl() == test_case.expected_transactional
    assert adapter.render_create_old_name_view_state_table_sql(
        database=test_case.database, schema="analytics"
    ).startswith(test_case.expected_state_table_prefix)
