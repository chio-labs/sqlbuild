"""Unit coverage for compatibility view SQL and column alias composition."""

from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ColumnInfo, RelationGrant
from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from sqlbuild.compiler.migrations.models import ColumnMigrationEvent
from sqlbuild.executor.migrations._helpers.old_name_views import (
    compose_column_aliases,
    reader_access_warning,
    reconcile_view_grants,
    render_old_name_view_select,
)
from sqlbuild.executor.migrations.models import OldNameViewSource
from tests.unit.src.sqlbuild.executor.migrations._helpers._test_types import (
    AdapterOldNameSqlTestCase,
    ComposeColumnAliasesTestCase,
    GrantReconcileTestCase,
    ReaderAccessWarningTestCase,
)
from tests.unit.src.sqlbuild.executor.migrations._helpers.helpers import (
    adapter_location,
    column_rename,
    old_name_plan_entry,
)

_ANALYSTS: RelationGrant = RelationGrant(privilege="SELECT", grantee="analysts")
_FUTURE: RelationGrant = RelationGrant(privilege="SELECT", grantee="reporting")


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


@pytest.mark.parametrize(
    "test_case",
    [
        ReaderAccessWarningTestCase(
            description="bigquery names principals that also need the destination table",
            adapter=BigQueryAdapter(),
            grants=(
                RelationGrant(privilege="roles/bigquery.dataViewer", grantee="group:b@example.com"),
                RelationGrant(privilege="roles/bigquery.dataViewer", grantee="group:a@example.com"),
            ),
            expected_warnings=(
                "M118: `analytics.revenue` now reads `analytics.daily_revenue` with each "
                "reader's own access. group:a@example.com, group:b@example.com kept their "
                "access to the old name but also need read access on "
                "`analytics.daily_revenue`; SQLBuild does not grant it",
            ),
        ),
        ReaderAccessWarningTestCase(
            description="bigquery without copied grants has nothing to warn about",
            adapter=BigQueryAdapter(),
            grants=(),
            expected_warnings=(),
        ),
        ReaderAccessWarningTestCase(
            description="postgres views read with the owner's access",
            adapter=PostgresAdapter(),
            grants=(RelationGrant(privilege="SELECT", grantee="orders_reader"),),
            expected_warnings=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_copied_grants_when_views_read_with_reader_access_then_m118_names_principals(
    test_case: ReaderAccessWarningTestCase,
) -> None:
    warnings: tuple[str, ...] = reader_access_warning(
        adapter=test_case.adapter,
        entry=old_name_plan_entry(adapter=test_case.adapter),
        grants=test_case.grants,
    )

    assert warnings == test_case.expected_warnings


@pytest.mark.parametrize(
    "test_case",
    [
        GrantReconcileTestCase(
            description="postgres revokes a default privilege the re-create added",
            adapter=PostgresAdapter(),
            current=(_ANALYSTS, _FUTURE),
            target=(_ANALYSTS,),
            expected_statements=('REVOKE SELECT ON analytics.revenue FROM "reporting"',),
        ),
        GrantReconcileTestCase(
            description="postgres grants what the drop removed, on exposed columns only",
            adapter=PostgresAdapter(),
            current=(),
            target=(
                _ANALYSTS,
                RelationGrant(privilege="SELECT", grantee="leads", column="amount"),
                RelationGrant(privilege="SELECT", grantee="leads", column="discount"),
            ),
            expected_statements=(
                'GRANT SELECT ON analytics.revenue TO "analysts"',
                'GRANT SELECT ("amount") ON analytics.revenue TO "leads"',
            ),
        ),
        GrantReconcileTestCase(
            description="postgres replaces a grant whose grant option changed",
            adapter=PostgresAdapter(),
            current=(RelationGrant(privilege="SELECT", grantee="analysts", grantable=True),),
            target=(_ANALYSTS,),
            expected_statements=(
                'REVOKE SELECT ON analytics.revenue FROM "analysts"',
                'GRANT SELECT ON analytics.revenue TO "analysts"',
            ),
        ),
        GrantReconcileTestCase(
            description="snowflake revokes a future grant copy grants reapplied",
            adapter=SnowflakeAdapter(),
            current=(RelationGrant(privilege="SELECT", grantee="REPORTING", grantee_kind="ROLE"),),
            target=(),
            expected_statements=('REVOKE SELECT ON VIEW analytics.revenue FROM ROLE "REPORTING"',),
        ),
        GrantReconcileTestCase(
            description="unchanged privileges issue nothing",
            adapter=PostgresAdapter(),
            current=(_ANALYSTS,),
            target=(_ANALYSTS,),
            expected_statements=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_view_grants_after_refresh_when_reconciling_then_they_equal_the_grants_before(
    test_case: GrantReconcileTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter: BaseAdapter = test_case.adapter
    executed: list[str] = []

    def columns(**_: Any) -> tuple[ColumnInfo, ...]:
        return (
            ColumnInfo(name="order_id", type="INTEGER"),
            ColumnInfo(name="amount", type="INTEGER"),
        )

    def current(**_: Any) -> tuple[RelationGrant, ...]:
        return test_case.current

    def execute(*, connection: Any, sql: str) -> None:
        del connection
        executed.append(sql)

    monkeypatch.setattr(adapter, "get_columns", columns)
    monkeypatch.setattr(adapter, "read_relation_grants", current)
    monkeypatch.setattr(adapter, "execute", execute)
    source: OldNameViewSource = OldNameViewSource(
        old=adapter_location(adapter=adapter, database=None, name="revenue"),
        new=adapter_location(adapter=adapter, database=None, name="daily_revenue"),
        column_aliases=(),
    )

    _ = reconcile_view_grants(
        adapter=adapter, connection=None, source=source, target=test_case.target
    )

    assert tuple(executed) == test_case.expected_statements
