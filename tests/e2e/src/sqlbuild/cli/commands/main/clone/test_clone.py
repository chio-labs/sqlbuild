"""E2E tests for sqb clone command."""

from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.clone._test_types import CloneE2ETestCase
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CloneE2ETestCase(
            description="clone copies tables recreates views and warns on missing source",
            repo_files={
                "sqlbuild_project.yml": dedent(
                    """
                    name: clone_project
                    adapter: duckdb
                    default_environment: dev

                    environments:
                      prod:
                        schema: prod
                        connection:
                          database: clone.duckdb
                        clone:
                          allow_as_source: true
                          allow_as_target: false

                      dev:
                        schema: dev
                        connection:
                          database: clone.duckdb
                        clone:
                          allow_as_source: true
                          allow_as_target: true
                    """
                ).strip()
                + "\n",
                "sources/raw.yml": dedent(
                    """
                    sources:
                      - name: raw_orders
                        expression: |
                          SELECT *
                          FROM (VALUES (1, 100), (2, 200))
                            AS raw_orders(order_id, amount_cents)
                    """
                ).strip()
                + "\n",
                "models/fact_orders.sql": dedent(
                    """
                    MODEL (materialized: table);

                    SELECT order_id, amount_cents FROM __source("raw_orders")
                    """
                ).strip()
                + "\n",
                "models/orders_enriched.sql": dedent(
                    """
                    MODEL (materialized: view);

                    SELECT order_id, amount_cents, amount_cents * 2 AS doubled_cents
                    FROM __ref("fact_orders")
                    """
                ).strip()
                + "\n",
                "models/missing_snapshot.sql": dedent(
                    """
                    MODEL (materialized: table);

                    SELECT 1 AS id
                    """
                ).strip()
                + "\n",
            },
            clone_command=(
                "--no-color",
                "clone",
                "--from",
                "prod",
                "--to",
                "dev",
                "--select",
                "fact_orders",
                "orders_enriched",
                "missing_snapshot",
            ),
            expected_exit_code=1,
            expected_stdout_fragments=(
                "fact_orders",
                "copied",
                "orders_enriched",
                "recreated_view",
                "missing_snapshot",
                "missing in source environment",
                "Completed with warnings.",
                "WARN=1",
            ),
            expected_query_results=(
                (
                    "SELECT order_id, amount_cents FROM dev.fact_orders ORDER BY order_id",
                    ((1, 100), (2, 200)),
                ),
                (
                    "SELECT order_id, doubled_cents FROM dev.orders_enriched ORDER BY order_id",
                    ((1, 200), (2, 400)),
                ),
            ),
        )
    ],
    ids=["clone copies tables recreates views and warns on missing source"],
)
def test_given_clone_command_when_running_then_managed_relations_sync_as_expected(
    test_case: CloneE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="clone_project",
        repo_files=test_case.repo_files,
    )
    db_path: Path = project_dir / "clone.duckdb"

    import duckdb

    prod_connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    prod_connection.execute("CREATE SCHEMA prod")
    prod_connection.execute("CREATE SCHEMA dev")
    prod_connection.execute(
        "CREATE TABLE prod.fact_orders AS "
        "SELECT * FROM (VALUES (1, 100), (2, 200)) AS t(order_id, amount_cents)"
    )
    prod_connection.execute(
        "CREATE OR REPLACE VIEW prod.orders_enriched AS "
        "SELECT order_id, amount_cents, amount_cents * 2 AS doubled_cents "
        "FROM prod.fact_orders"
    )
    prod_connection.close()

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.clone_command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout, result.stdout + result.stderr

    query: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query, expected_rows in test_case.expected_query_results:
        actual_rows: list[tuple[object, ...]] = query_duckdb(db_path=db_path, sql=query)
        assert tuple(tuple(row) for row in actual_rows) == expected_rows
