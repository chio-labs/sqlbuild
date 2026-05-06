"""E2E tests for expression-backed source declarations."""

from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    ExpressionSourceBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    query_duckdb,
    run_sqb,
    table_exists,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ExpressionSourceBuildE2ETestCase(
            description="blank project builds from inline expression sources",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                name = "expression_source_project"
                adapter = "duckdb"

                [connection]
                database = "expression_sources.duckdb"

                [defaults]
                materialized = "table"
                    """
                ).strip()
                + "\n",
                "sources/raw.yml": dedent(
                    """
                    sources:
                      - name: raw_orders
                        expression: |
                          SELECT * FROM (VALUES
                            (1, '1', '2026-01-01 00:30:00', 100),
                            (2, '2', '2026-01-01 01:30:00', 200)
                          ) AS orders(order_id, customer_id, ordered_at, amount_cents)
                        type_enforcement: true
                        columns:
                          - name: order_id
                            type: INTEGER
                          - name: customer_id
                            type: INTEGER
                          - name: ordered_at
                            type: TIMESTAMP
                          - name: amount_cents
                            type: INTEGER
                    """
                ).strip()
                + "\n",
                "models/fact_orders.sql": dedent(
                    """
                    MODEL (materialized table);

                    SELECT
                      order_id,
                      customer_id,
                      ordered_at,
                      amount_cents
                    FROM __source("raw_orders")
                    """
                ).strip()
                + "\n",
            },
            command=("--no-color", "build"),
            expected_exit_code=0,
            expected_table_names=("fact_orders",),
            expected_query_results=(
                (
                    (
                        "SELECT order_id, customer_id, amount_cents "
                        "FROM main.fact_orders ORDER BY order_id"
                    ),
                    ((1, 1, 100), (2, 2, 200)),
                ),
            ),
            expected_runtime_fragments=(
                "CAST(customer_id AS INTEGER) AS customer_id",
                "FROM (SELECT * FROM (VALUES",
            ),
        )
    ],
    ids=["blank project builds from inline expression sources"],
)
def test_given_expression_source_when_building_then_inline_source_sql_is_used(
    test_case: ExpressionSourceBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="expression_source_project",
        repo_files=test_case.repo_files,
    )
    db_path: Path = project_dir / "expression_sources.duckdb"

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr

    table_name: str
    for table_name in test_case.expected_table_names:
        assert table_exists(db_path=db_path, table_name=table_name)

    query: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query, expected_rows in test_case.expected_query_results:
        actual_rows: list[tuple[object, ...]] = query_duckdb(db_path=db_path, sql=query)
        assert tuple(tuple(row) for row in actual_rows) == expected_rows

    runtime_sql: str = (project_dir / "target" / "run" / "models" / "fact_orders.sql").read_text(
        encoding="utf-8"
    )
    fragment: str
    for fragment in test_case.expected_runtime_fragments:
        assert fragment in runtime_sql
