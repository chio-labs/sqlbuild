"""Helpers for diff e2e tests."""

from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb


def prepare_diff_project(tmp_path: Path) -> Path:
    """Create a small inline project for diff e2e tests."""

    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name="diff_project",
        repo_files={
            "sqlbuild_project.toml": dedent(
                """
                name = "diff_project"
                adapter = "duckdb"
                default_target = "dev"

                [connection]
                database = "diff.duckdb"

                [targets.prod]
                schema = "prod"

                [targets.dev]
                schema = "dev"

                [defaults]
                materialized = "table"

                [path_defaults.staging]
                materialized = "view"
                """
            ).strip()
            + "\n",
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_orders
                    expression: |
                      SELECT * FROM (VALUES
                        (1, 1, TIMESTAMP '2026-04-01 09:15:00', 'placed', 100),
                        (2, 2, TIMESTAMP '2026-04-02 10:00:00', 'placed', 200),
                        (3, 1, TIMESTAMP '2026-04-03 11:30:00', 'placed', 300)
                      ) AS raw_orders(order_id, customer_id, ordered_at, status, amount_cents)
                """
            ).strip()
            + "\n",
            "models/staging/stg_orders.sql": dedent(
                """
                MODEL (materialized view);

                SELECT
                  order_id,
                  customer_id,
                  ordered_at,
                  status,
                  amount_cents
                FROM __source("raw_orders")
                """
            ).strip()
            + "\n",
            "models/intermediate/orders_snapshot.sql": dedent(
                """
                MODEL (
                  materialized table,
                  unique_key [order_id],
                  cursor ordered_at,
                  cursor_type timestamp,
                  row_diff_exclude_columns [status],
                  row_diff_tolerances (
                    by_column (
                      amount_cents (
                        absolute 1,
                      ),
                    ),
                  ),
                );

                SELECT
                  order_id,
                  customer_id,
                  ordered_at,
                  status,
                  amount_cents
                FROM __ref("stg_orders")
                """
            ).strip()
            + "\n",
            "models/intermediate/customer_totals.sql": dedent(
                """
                MODEL (
                  materialized table,
                  unique_key [customer_id]
                );

                SELECT
                  customer_id,
                  COUNT(*) AS order_count,
                  SUM(amount_cents) AS total_amount_cents
                FROM __ref("stg_orders")
                GROUP BY customer_id
                """
            ).strip()
            + "\n",
            "models/intermediate/orders_sparse.sql": dedent(
                """
                MODEL (
                  materialized table,
                  unique_key [order_id]
                );

                SELECT
                  order_id,
                  customer_id
                FROM __ref("stg_orders")
                WHERE order_id <= 2
                """
            ).strip()
            + "\n",
            "models/marts/daily_revenue.sql": dedent(
                """
                MODEL (materialized table);

                SELECT
                  CAST(ordered_at AS DATE) AS revenue_date,
                  SUM(amount_cents) AS total_amount_cents
                FROM __ref("orders_snapshot")
                GROUP BY CAST(ordered_at AS DATE)
                """
            ).strip()
            + "\n",
        },
    )


def build_environment(*, project_dir: Path, environment: str) -> None:
    """Build one environment for the diff fixture."""

    (project_dir / "sqlbuild_local.toml").write_text(
        f'target = "{environment}"\n',
        encoding="utf-8",
    )
    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def build_both_environments(*, project_dir: Path) -> None:
    """Build prod then dev from a blank db."""

    db_path: Path = project_dir / "diff.duckdb"
    db_path.unlink(missing_ok=True)
    build_environment(project_dir=project_dir, environment="prod")
    build_environment(project_dir=project_dir, environment="dev")


def execute_duckdb(*, db_path: Path, sql: str) -> None:
    """Execute mutating SQL against a DuckDB file."""

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    try:
        connection.execute(sql)
    finally:
        connection.close()
