from __future__ import annotations

from collections.abc import Callable
from itertools import product

import pytest

from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from tests.unit.src.sqlbuild.adapters._test_types import AdapterStateTableDdlTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        AdapterStateTableDdlTestCase(
            description=f"{adapter_name} {render_method}",
            adapter=adapter,
            render_method=render_method,
            expected_create_fragment=create_fragment,
        )
        for (adapter_name, adapter, create_fragment), render_method in product(
            (
                ("duckdb", DuckDbAdapter(), "CREATE TABLE IF NOT EXISTS "),
                ("postgres", PostgresAdapter(), "CREATE TABLE IF NOT EXISTS "),
                ("bigquery", BigQueryAdapter(), "CREATE TABLE IF NOT EXISTS "),
                ("databricks", DatabricksAdapter(), "CREATE TABLE IF NOT EXISTS "),
                ("sql server", SqlServerAdapter(), "CREATE TABLE "),
            ),
            (
                "render_create_fingerprint_table_sql",
                "render_create_source_freshness_table_sql",
                "render_create_node_result_table_sql",
                "render_create_audit_result_table_sql",
                "render_create_janitor_event_table_sql",
                "render_create_migration_state_table_sql",
                "render_create_old_name_view_state_table_sql",
                "render_create_column_migration_state_table_sql",
                "render_create_microbatch_state_table_sql",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_non_snowflake_adapter_when_rendering_state_table_then_permanent_without_retention(
    test_case: AdapterStateTableDdlTestCase,
) -> None:
    render: Callable[..., str] = getattr(test_case.adapter, test_case.render_method)

    sql: str = render(database="analytics", schema="marts")

    assert test_case.expected_create_fragment in sql
    assert "TRANSIENT" not in sql.upper()
    assert "DATA_RETENTION_TIME_IN_DAYS" not in sql.upper()
