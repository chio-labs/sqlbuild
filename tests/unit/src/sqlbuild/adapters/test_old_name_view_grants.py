"""Unit coverage for replaying an archived relation's privileges onto a compatibility view."""

from __future__ import annotations

import pytest

from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from tests.unit.src.sqlbuild.adapters._test_types import RelationGrantCaptureTestCase
from tests.unit.src.sqlbuild.adapters.helpers import GrantConnection, grant_execute

_ARCHIVE: str = "_sqb_archive__20260928t101500z__migration_origin__revenue"


@pytest.mark.parametrize(
    "test_case",
    [
        RelationGrantCaptureTestCase(
            description="duckdb has no object privileges",
            adapter=DuckDbAdapter(),
            relation_type="table",
            rows=[],
            destination="analytics.revenue",
            expected_query_fragment="",
            expected_statements=(),
        ),
        RelationGrantCaptureTestCase(
            description="postgres replays table privileges and public grants",
            adapter=PostgresAdapter(),
            relation_type="table",
            rows=[("SELECT", None, False), ("SELECT", "orders_reader", True)],
            destination="analytics.revenue",
            expected_query_fragment="aclexplode(relation.relacl)",
            expected_statements=(
                "GRANT SELECT ON analytics.revenue TO PUBLIC",
                'GRANT SELECT ON analytics.revenue TO "orders_reader" WITH GRANT OPTION',
            ),
        ),
        RelationGrantCaptureTestCase(
            description="snowflake keeps view privileges and grant option, skips ownership",
            adapter=SnowflakeAdapter(),
            relation_type="table",
            rows=[
                ("t", "OWNERSHIP", "TABLE", _ARCHIVE, "ROLE", "TRANSFORMER", "true", "SYSADMIN"),
                ("t", "SELECT", "TABLE", _ARCHIVE, "ROLE", "REPORTING", "true", "TRANSFORMER"),
                ("t", "INSERT", "TABLE", _ARCHIVE, "ROLE", "LOADER", "false", "TRANSFORMER"),
                ("t", "SELECT", "TABLE", _ARCHIVE, "DATABASE_ROLE", "ORDERS.READ", "false", "X"),
                ("t", "SELECT", "TABLE", _ARCHIVE, "SHARE", "PARTNER_SHARE", "false", "X"),
            ],
            destination="analytics.revenue",
            expected_query_fragment=f"SHOW GRANTS ON TABLE analytics.{_ARCHIVE}",
            expected_statements=(
                'GRANT SELECT ON VIEW analytics.revenue TO ROLE "REPORTING" WITH GRANT OPTION',
                'GRANT SELECT ON VIEW analytics.revenue TO DATABASE ROLE "ORDERS"."READ"',
            ),
        ),
        RelationGrantCaptureTestCase(
            description="snowflake reads grants of an archived view model as a view",
            adapter=SnowflakeAdapter(),
            relation_type="VIEW",
            rows=[("t", "SELECT", "VIEW", _ARCHIVE, "ROLE", "REPORTING", "false", "X")],
            destination="analytics.revenue",
            expected_query_fragment=f"SHOW GRANTS ON VIEW analytics.{_ARCHIVE}",
            expected_statements=('GRANT SELECT ON VIEW analytics.revenue TO ROLE "REPORTING"',),
        ),
        RelationGrantCaptureTestCase(
            description="databricks replays direct unity catalog grants that apply to views",
            adapter=DatabricksAdapter(),
            relation_type="table",
            rows=[
                ("analysts", "SELECT", "TABLE", "main.analytics.x"),
                ("loaders", "MODIFY", "TABLE", "main.analytics.x"),
                ("owners", "OWN", "TABLE", "main.analytics.x"),
                ("everyone", "USE SCHEMA", "SCHEMA", "main.analytics"),
            ],
            destination="`main`.`analytics`.`revenue`",
            expected_query_fragment="SHOW GRANTS ON TABLE",
            expected_statements=(
                "GRANT SELECT ON VIEW `main`.`analytics`.`revenue` TO `analysts`",
            ),
        ),
        RelationGrantCaptureTestCase(
            description="sql server replays grants, grant options, and denies",
            adapter=SqlServerAdapter(),
            relation_type="table",
            rows=[
                ("GRANT", "SELECT", "reporting"),
                ("GRANT_WITH_GRANT_OPTION", "SELECT", "leads"),
                ("DENY", "UPDATE", "reporting"),
                ("GRANT", "EXECUTE", "reporting"),
            ],
            destination="[analytics].[revenue]",
            expected_query_fragment="sys.database_permissions",
            expected_statements=(
                "GRANT SELECT ON OBJECT::[analytics].[revenue] TO [reporting]",
                "GRANT SELECT ON OBJECT::[analytics].[revenue] TO [leads] WITH GRANT OPTION",
                "DENY UPDATE ON OBJECT::[analytics].[revenue] TO [reporting]",
            ),
        ),
        RelationGrantCaptureTestCase(
            description="bigquery replays table iam role bindings",
            adapter=BigQueryAdapter(),
            relation_type="table",
            rows=[("roles/bigquery.dataViewer", "group:analysts@example.com")],
            destination="orders-project.analytics.revenue",
            expected_query_fragment=(
                "`orders-project.region-us`.INFORMATION_SCHEMA.OBJECT_PRIVILEGES"
            ),
            expected_statements=(
                "GRANT `roles/bigquery.dataViewer` ON VIEW `orders-project.analytics.revenue` "
                'TO "group:analysts@example.com"',
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_archived_relation_grants_when_capturing_then_view_statements_copy_them(
    test_case: RelationGrantCaptureTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection: GrantConnection = GrantConnection(test_case.rows)
    monkeypatch.setattr(test_case.adapter, "execute", grant_execute(connection))

    statements: tuple[str, ...] = test_case.adapter.capture_relation_grants(
        connection=connection,
        database=None,
        schema="analytics",
        name=_ARCHIVE,
        relation_type=test_case.relation_type,
        destination=test_case.destination,
    )

    assert statements == test_case.expected_statements
    assert test_case.expected_query_fragment in "".join(connection.executed)


@pytest.mark.parametrize(
    "test_case",
    [
        RelationGrantCaptureTestCase(
            description="bigquery re-creates a view it cannot rename, then drops the old one",
            adapter=BigQueryAdapter(),
            relation_type="view",
            rows=[("SELECT order_id FROM `orders-project.analytics.daily_revenue`",)],
            destination=f"orders-project.analytics.{_ARCHIVE}",
            expected_query_fragment="`orders-project.analytics`.INFORMATION_SCHEMA.VIEWS",
            expected_statements=(
                f"CREATE VIEW `orders-project.analytics.{_ARCHIVE}` AS "
                "SELECT order_id FROM `orders-project.analytics.daily_revenue`",
                "DROP VIEW `orders-project.analytics.revenue`",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_bigquery_view_when_archiving_then_definition_moves_to_the_archive_name(
    test_case: RelationGrantCaptureTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection: GrantConnection = GrantConnection(test_case.rows)
    monkeypatch.setattr(test_case.adapter, "execute", grant_execute(connection))
    recorder: StatementRecorder = StatementRecorder()

    test_case.adapter.rename_view(
        connection=connection,
        origin="orders-project.analytics.revenue",
        destination=test_case.destination,
        statement_recorder=recorder,
    )

    assert test_case.expected_query_fragment in connection.executed[0]
    assert tuple(connection.executed[1:]) == test_case.expected_statements
