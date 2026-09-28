"""Unit coverage for reading and replaying relation privileges onto a compatibility view."""

from __future__ import annotations

import pytest

from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import RelationGrant
from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from tests.unit.src.sqlbuild.adapters._test_types import (
    RelationGrantCaptureTestCase,
    ViewReplaceTestCase,
)
from tests.unit.src.sqlbuild.adapters.helpers import GrantConnection, grant_execute

_ARCHIVE: str = "_sqb_archive__20260928t101500z__migration_origin__revenue"
_EXPOSED: tuple[str, ...] = ("order_id", "amount")


@pytest.mark.parametrize(
    "test_case",
    [
        RelationGrantCaptureTestCase(
            description="duckdb has no object privileges",
            adapter=DuckDbAdapter(),
            relation_type="table",
            answers=(),
            destination="analytics.revenue",
            columns=_EXPOSED,
            expected_query_fragment="",
            expected_statements=(),
        ),
        RelationGrantCaptureTestCase(
            description="postgres replays table privileges and public grants",
            adapter=PostgresAdapter(),
            relation_type="table",
            answers=([("SELECT", None, False), ("SELECT", "orders_reader", True)], []),
            destination="analytics.revenue",
            columns=_EXPOSED,
            expected_query_fragment="aclexplode(relation.relacl)",
            expected_statements=(
                "GRANT SELECT ON analytics.revenue TO PUBLIC",
                'GRANT SELECT ON analytics.revenue TO "orders_reader" WITH GRANT OPTION',
            ),
        ),
        RelationGrantCaptureTestCase(
            description="postgres replays column privileges only on columns the view exposes",
            adapter=PostgresAdapter(),
            relation_type="table",
            answers=(
                [],
                [
                    ("amount", "SELECT", "orders_reader", False),
                    ("discount", "SELECT", "orders_reader", False),
                    ("order_id", "UPDATE", None, True),
                ],
            ),
            destination="analytics.revenue",
            columns=_EXPOSED,
            expected_query_fragment="aclexplode(attribute.attacl)",
            expected_statements=(
                'GRANT SELECT ("amount") ON analytics.revenue TO "orders_reader"',
                'GRANT UPDATE ("order_id") ON analytics.revenue TO PUBLIC WITH GRANT OPTION',
            ),
        ),
        RelationGrantCaptureTestCase(
            description="snowflake keeps view privileges and grant option, skips ownership",
            adapter=SnowflakeAdapter(),
            relation_type="table",
            answers=(
                [
                    ("t", "OWNERSHIP", "TABLE", _ARCHIVE, "ROLE", "TRANSFORMER", "true", "X"),
                    ("t", "SELECT", "TABLE", _ARCHIVE, "ROLE", "REPORTING", "true", "X"),
                    ("t", "INSERT", "TABLE", _ARCHIVE, "ROLE", "LOADER", "false", "X"),
                    (
                        "t",
                        "SELECT",
                        "TABLE",
                        _ARCHIVE,
                        "DATABASE_ROLE",
                        "ORDERS.READ",
                        "false",
                        "X",
                    ),
                    ("t", "SELECT", "TABLE", _ARCHIVE, "SHARE", "PARTNER_SHARE", "false", "X"),
                ],
            ),
            destination="analytics.revenue",
            columns=_EXPOSED,
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
            answers=([("t", "SELECT", "VIEW", _ARCHIVE, "ROLE", "REPORTING", "false", "X")],),
            destination="analytics.revenue",
            columns=_EXPOSED,
            expected_query_fragment=f"SHOW GRANTS ON VIEW analytics.{_ARCHIVE}",
            expected_statements=('GRANT SELECT ON VIEW analytics.revenue TO ROLE "REPORTING"',),
        ),
        RelationGrantCaptureTestCase(
            description="databricks replays direct unity catalog grants that apply to views",
            adapter=DatabricksAdapter(),
            relation_type="table",
            answers=(
                [
                    ("analysts", "SELECT", "TABLE", "main.analytics.x"),
                    ("loaders", "MODIFY", "TABLE", "main.analytics.x"),
                    ("owners", "OWN", "TABLE", "main.analytics.x"),
                    ("everyone", "USE SCHEMA", "SCHEMA", "main.analytics"),
                ],
            ),
            destination="`main`.`analytics`.`revenue`",
            columns=_EXPOSED,
            expected_query_fragment="SHOW GRANTS ON TABLE",
            expected_statements=(
                "GRANT SELECT ON VIEW `main`.`analytics`.`revenue` TO `analysts`",
            ),
        ),
        RelationGrantCaptureTestCase(
            description="sql server replays object grants, grant options, and denies",
            adapter=SqlServerAdapter(),
            relation_type="table",
            answers=(
                [
                    ("GRANT", "SELECT", "reporting", None),
                    ("GRANT_WITH_GRANT_OPTION", "SELECT", "leads", None),
                    ("DENY", "UPDATE", "reporting", None),
                    ("GRANT", "EXECUTE", "reporting", None),
                ],
            ),
            destination="[analytics].[revenue]",
            columns=_EXPOSED,
            expected_query_fragment="sys.database_permissions",
            expected_statements=(
                "GRANT SELECT ON OBJECT::[analytics].[revenue] TO [reporting]",
                "GRANT SELECT ON OBJECT::[analytics].[revenue] TO [leads] WITH GRANT OPTION",
                "DENY UPDATE ON OBJECT::[analytics].[revenue] TO [reporting]",
            ),
        ),
        RelationGrantCaptureTestCase(
            description="sql server keeps column denies on exposed columns after object grants",
            adapter=SqlServerAdapter(),
            relation_type="table",
            answers=(
                [
                    ("DENY", "SELECT", "reporting", "amount"),
                    ("GRANT", "SELECT", "reporting", None),
                    ("GRANT", "SELECT", "leads", "order_id"),
                    ("DENY", "SELECT", "reporting", "discount"),
                ],
            ),
            destination="[analytics].[revenue]",
            columns=_EXPOSED,
            expected_query_fragment="COL_NAME(permission.major_id, NULLIF(permission.minor_id, 0))",
            expected_statements=(
                "GRANT SELECT ON OBJECT::[analytics].[revenue] TO [reporting]",
                "DENY SELECT ON OBJECT::[analytics].[revenue] ([amount]) TO [reporting]",
                "GRANT SELECT ON OBJECT::[analytics].[revenue] ([order_id]) TO [leads]",
            ),
        ),
        RelationGrantCaptureTestCase(
            description="bigquery replays table iam role bindings",
            adapter=BigQueryAdapter(),
            relation_type="table",
            answers=([("roles/bigquery.dataViewer", "group:analysts@example.com")],),
            destination="orders-project.analytics.revenue",
            columns=_EXPOSED,
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
def test_given_archived_relation_grants_when_replaying_then_view_statements_copy_them(
    test_case: RelationGrantCaptureTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection: GrantConnection = GrantConnection(test_case.answers)
    monkeypatch.setattr(test_case.adapter, "execute", grant_execute(connection))

    grants: tuple[RelationGrant, ...] = test_case.adapter.read_relation_grants(
        connection=connection,
        database=None,
        schema="analytics",
        name=_ARCHIVE,
        relation_type=test_case.relation_type,
    )
    statements: tuple[str, ...] = test_case.adapter.render_relation_grants(
        grants=grants, destination=test_case.destination, columns=test_case.columns
    )

    assert statements == test_case.expected_statements
    assert test_case.expected_query_fragment in "".join(connection.executed)


@pytest.mark.parametrize(
    "test_case",
    [
        RelationGrantCaptureTestCase(
            description="bigquery copies the view's iam bindings to the archive before dropping",
            adapter=BigQueryAdapter(),
            relation_type="view",
            answers=(
                [("SELECT order_id FROM `orders-project.analytics.daily_revenue`",)],
                [("roles/bigquery.dataViewer", "group:analysts@example.com")],
            ),
            destination=f"orders-project.analytics.{_ARCHIVE}",
            columns=(),
            expected_query_fragment="INFORMATION_SCHEMA.OBJECT_PRIVILEGES",
            expected_statements=(
                f"CREATE VIEW `orders-project.analytics.{_ARCHIVE}` AS "
                "SELECT order_id FROM `orders-project.analytics.daily_revenue`",
                "GRANT `roles/bigquery.dataViewer` ON VIEW "
                f'`orders-project.analytics.{_ARCHIVE}` TO "group:analysts@example.com"',
                "DROP VIEW `orders-project.analytics.revenue`",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_bigquery_view_when_archiving_then_definition_and_grants_move_before_drop(
    test_case: RelationGrantCaptureTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection: GrantConnection = GrantConnection(test_case.answers)
    monkeypatch.setattr(test_case.adapter, "execute", grant_execute(connection))
    recorder: StatementRecorder = StatementRecorder()

    test_case.adapter.rename_view(
        connection=connection,
        origin="orders-project.analytics.revenue",
        destination=test_case.destination,
        statement_recorder=recorder,
    )

    assert "INFORMATION_SCHEMA.VIEWS" in connection.executed[0]
    assert test_case.expected_query_fragment in connection.executed[1]
    assert tuple(connection.executed[2:]) == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        ViewReplaceTestCase(
            description="postgres create or replace keeps privileges",
            adapter=PostgresAdapter(),
            expected_statements=("CREATE OR REPLACE VIEW analytics.revenue AS SELECT 1",),
        ),
        ViewReplaceTestCase(
            description="snowflake copies grants onto the replacement",
            adapter=SnowflakeAdapter(),
            expected_statements=(
                "CREATE OR REPLACE VIEW analytics.revenue COPY GRANTS AS SELECT 1",
            ),
        ),
        ViewReplaceTestCase(
            description="sql server alters the view in place",
            adapter=SqlServerAdapter(),
            expected_statements=("ALTER VIEW analytics.revenue AS SELECT 1",),
        ),
        ViewReplaceTestCase(
            description="databricks alters the view in place",
            adapter=DatabricksAdapter(),
            expected_statements=("ALTER VIEW analytics.revenue AS SELECT 1",),
        ),
        ViewReplaceTestCase(
            description="bigquery has no privilege-preserving replace",
            adapter=BigQueryAdapter(),
            expected_statements=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_existing_view_when_redefining_then_adapter_keeps_its_privileges(
    test_case: ViewReplaceTestCase,
) -> None:
    statements: tuple[str, ...] | None = test_case.adapter.render_replace_view_keeping_grants(
        destination="analytics.revenue", sql="SELECT 1"
    )

    assert statements == test_case.expected_statements
