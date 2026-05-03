"""E2E tests for query-change propagation behavior."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    QueryPropagationBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    run_sqb,
)

TEST_CASES: list[QueryPropagationBuildE2ETestCase] = [
    QueryPropagationBuildE2ETestCase(
        description="warn-only query change does not propagate downstream",
        repo_files={
            "sqlbuild_project.yml": dedent(
                """
                name: query_propagation_project
                adapter: duckdb

                connection:
                  database: propagation.duckdb

                defaults:
                  materialized: table
                """
            ).strip()
            + "\n",
            "seed_raw_data.sql": dedent(
                """
                CREATE TABLE IF NOT EXISTS raw_orders (
                  id INTEGER,
                  ordered_at TIMESTAMP,
                  amount_cents INTEGER
                );

                INSERT INTO raw_orders VALUES
                  (1, '2026-01-01 00:30:00', 100),
                  (2, '2026-01-01 01:30:00', 200);
                """
            ).strip()
            + "\n",
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_orders
                    schema: main
                    table: raw_orders
                """
            ).strip()
            + "\n",
            "models/staging/stg_orders.sql": dedent(
                """
                MODEL (materialized view);

                SELECT id AS order_id, ordered_at, amount_cents FROM __source("raw_orders")
                """
            ).strip()
            + "\n",
            "models/marts/fact_orders.sql": dedent(
                """
                MODEL (materialized table);

                SELECT order_id, ordered_at, amount_cents AS line_total_cents
                FROM __ref("stg_orders")
                """
            ).strip()
            + "\n",
            "models/marts/hourly_order_activity.sql": dedent(
                """
                MODEL (
                  materialized incremental,
                  incremental_strategy delete_insert,
                  cursor activity_hour,
                  cursor_type timestamp,
                  cursor_grain hour,
                  cursor_inputs (
                    fact_orders ordered_at,
                  ),
                  incremental_mode microbatch,
                  batch_size 1d,
                );

                SELECT
                  DATE_TRUNC('hour', ordered_at) AS activity_hour,
                  COUNT(*) AS orders_placed,
                  SUM(line_total_cents) AS revenue_cents
                FROM __ref("fact_orders")
                GROUP BY DATE_TRUNC('hour', ordered_at)
                """
            ).strip()
            + "\n",
            "models/marts/daily_activity_rollup.sql": dedent(
                """
                MODEL (
                  materialized incremental,
                  incremental_strategy delete_insert,
                  cursor activity_day,
                  cursor_type timestamp,
                  cursor_grain day,
                  cursor_inputs (
                    hourly_order_activity activity_hour,
                  ),
                  incremental_mode microbatch,
                  batch_size 2d,
                  query_change_backfill bounded-14d
                );

                SELECT
                  DATE_TRUNC('day', activity_hour) AS activity_day,
                  SUM(orders_placed) AS orders_placed,
                  SUM(revenue_cents) AS revenue_cents
                FROM __ref("hourly_order_activity")
                GROUP BY DATE_TRUNC('day', activity_hour)
                """
            ).strip()
            + "\n",
        },
        initial_build_command=("--no-color", "build"),
        plan_command=("plan", "--json"),
        mutation_file="models/marts/hourly_order_activity.sql",
        before_text="SUM(line_total_cents) AS revenue_cents",
        after_text="SUM(line_total_cents) + 0 AS revenue_cents",
        expected_exit_code=0,
        expected_reasons={
            "hourly_order_activity": "query_changed",
            "daily_activity_rollup": "normal_incremental",
        },
    ),
    QueryPropagationBuildE2ETestCase(
        description="bounded query change propagates downstream",
        repo_files={
            "sqlbuild_project.yml": dedent(
                """
                name: query_propagation_project
                adapter: duckdb

                connection:
                  database: propagation.duckdb

                defaults:
                  materialized: table
                """
            ).strip()
            + "\n",
            "seed_raw_data.sql": dedent(
                """
                CREATE TABLE IF NOT EXISTS raw_orders (
                  id INTEGER,
                  ordered_at TIMESTAMP,
                  amount_cents INTEGER
                );

                INSERT INTO raw_orders VALUES
                  (1, '2026-01-01 00:30:00', 100),
                  (2, '2026-01-01 01:30:00', 200);
                """
            ).strip()
            + "\n",
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_orders
                    schema: main
                    table: raw_orders
                """
            ).strip()
            + "\n",
            "models/staging/stg_orders.sql": dedent(
                """
                MODEL (materialized view);

                SELECT id AS order_id, ordered_at, amount_cents FROM __source("raw_orders")
                """
            ).strip()
            + "\n",
            "models/marts/fact_orders.sql": dedent(
                """
                MODEL (materialized table);

                SELECT order_id, ordered_at, amount_cents AS line_total_cents
                FROM __ref("stg_orders")
                """
            ).strip()
            + "\n",
            "models/marts/hourly_order_activity.sql": dedent(
                """
                MODEL (
                  materialized incremental,
                  incremental_strategy delete_insert,
                  cursor activity_hour,
                  cursor_type timestamp,
                  cursor_grain hour,
                  cursor_inputs (
                    fact_orders ordered_at,
                  ),
                  incremental_mode microbatch,
                  batch_size 1d,
                  query_change_backfill bounded-14d
                );

                SELECT
                  DATE_TRUNC('hour', ordered_at) AS activity_hour,
                  COUNT(*) AS orders_placed,
                  SUM(line_total_cents) AS revenue_cents
                FROM __ref("fact_orders")
                GROUP BY DATE_TRUNC('hour', ordered_at)
                """
            ).strip()
            + "\n",
            "models/marts/daily_activity_rollup.sql": dedent(
                """
                MODEL (
                  materialized incremental,
                  incremental_strategy delete_insert,
                  cursor activity_day,
                  cursor_type timestamp,
                  cursor_grain day,
                  cursor_inputs (
                    hourly_order_activity activity_hour,
                  ),
                  incremental_mode microbatch,
                  batch_size 2d,
                  query_change_backfill bounded-14d
                );

                SELECT
                  DATE_TRUNC('day', activity_hour) AS activity_day,
                  SUM(orders_placed) AS orders_placed,
                  SUM(revenue_cents) AS revenue_cents
                FROM __ref("hourly_order_activity")
                GROUP BY DATE_TRUNC('day', activity_hour)
                """
            ).strip()
            + "\n",
        },
        initial_build_command=("--no-color", "build"),
        plan_command=("plan", "--json"),
        mutation_file="models/marts/hourly_order_activity.sql",
        before_text="SUM(line_total_cents) AS revenue_cents",
        after_text="SUM(line_total_cents) + 0 AS revenue_cents",
        expected_exit_code=0,
        expected_reasons={
            "hourly_order_activity": "query_changed",
            "daily_activity_rollup": "upstream_changed",
        },
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_changed_upstream_when_planning_then_downstream_reason_matches_policy(
    test_case: QueryPropagationBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="query_propagation_project",
        repo_files=test_case.repo_files,
    )
    db_path: Path = project_dir / "propagation.duckdb"

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    connection.execute((project_dir / "seed_raw_data.sql").read_text(encoding="utf-8"))
    connection.close()

    initial_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.initial_build_command,
        project_dir=project_dir,
    )
    assert initial_result.returncode == test_case.expected_exit_code, (
        initial_result.stdout + initial_result.stderr
    )

    mutation_path: Path = project_dir / test_case.mutation_file
    original_text: str = mutation_path.read_text(encoding="utf-8")
    mutation_path.write_text(
        original_text.replace(test_case.before_text, test_case.after_text),
        encoding="utf-8",
    )

    try:
        plan_result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.plan_command,
            project_dir=project_dir,
        )
        assert plan_result.returncode == test_case.expected_exit_code, (
            plan_result.stdout + plan_result.stderr
        )
        payload: dict[str, object] = json.loads(plan_result.stdout)
        reasons_by_name: dict[str, str] = {
            str(entry["name"]): str(entry["reason"])
            for entry in payload["models"]
            if str(entry["name"]) in test_case.expected_reasons
        }
        assert reasons_by_name == test_case.expected_reasons
    finally:
        mutation_path.write_text(original_text, encoding="utf-8")
