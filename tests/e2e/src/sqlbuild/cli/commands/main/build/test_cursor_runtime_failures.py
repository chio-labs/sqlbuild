"""E2E tests for direct cursor-related failure paths."""

from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    CliFailureBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    run_sqb,
)

TEST_CASES: list[CliFailureBuildE2ETestCase] = [
    CliFailureBuildE2ETestCase(
        description="bad mapped cursor input column fails at runtime",
        repo_files={
            "sqlbuild_project.yml": (
                "name: cursor_runtime_project\n"
                "adapter: duckdb\n"
                "connection:\n"
                "  database: cursor_runtime.duckdb\n"
            ),
            "seed_raw_data.sql": (
                "CREATE TABLE main.raw_orders (id INTEGER, ordered_at TIMESTAMP);\n"
                "INSERT INTO main.raw_orders VALUES (1, '2026-01-01 00:30:00');\n"
                "CREATE TABLE main.customer_status_snapshot "
                "(customer_id INTEGER, last_ordered_at TIMESTAMP);\n"
            ),
            "models/stg_orders.sql": (
                "MODEL (materialized view);\n\n"
                "SELECT id AS order_id, ordered_at FROM main.raw_orders\n"
            ),
            "models/fact_orders.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT order_id, ordered_at FROM __ref("stg_orders")\n'
            ),
            "models/customer_status_snapshot.sql": dedent(
                """
                MODEL (
                  materialized incremental,
                  incremental_strategy merge,
                  unique_key [customer_id],
                  cursor last_ordered_at,
                  cursor_type timestamp,
                  cursor_grain second,
                  cursor_inputs (
                    fact_orders missing_column,
                  ),
                );

                SELECT 1 AS customer_id, MAX(ordered_at) AS last_ordered_at
                FROM __ref("fact_orders")
                """
            ).strip()
            + "\n",
        },
        command=("--no-color", "build", "--select", "+customer_status_snapshot"),
        expected_exit_code=1,
        expected_stderr_fragments=(),
        expected_stdout_fragments=("missing_column",),
    ),
    CliFailureBuildE2ETestCase(
        description="broken runtime-owned upstream relation fails at compile time",
        repo_files={
            "sqlbuild_project.yml": (
                "name: cursor_runtime_project\n"
                "adapter: duckdb\n"
                "connection:\n"
                "  database: cursor_runtime.duckdb\n"
            ),
            "seed_raw_data.sql": (
                "CREATE TABLE main.raw_orders (id INTEGER, ordered_at TIMESTAMP);\n"
            ),
            "models/customer_status_snapshot.sql": dedent(
                """
                MODEL (
                  materialized incremental,
                  incremental_strategy merge,
                  unique_key [customer_id],
                  cursor last_ordered_at,
                  cursor_type timestamp,
                  cursor_grain second,
                  cursor_inputs (
                    missing_orders ordered_at,
                  ),
                );

                SELECT 1 AS customer_id, MAX(ordered_at) AS last_ordered_at
                FROM __ref("missing_orders")
                """
            ).strip()
            + "\n",
        },
        command=("--no-color", "build", "--select", "customer_status_snapshot"),
        expected_exit_code=1,
        expected_stderr_fragments=("references unknown model 'missing_orders'",),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_cursor_runtime_failure_projects_when_running_build_then_cli_fails_clearly(
    test_case: CliFailureBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="cursor_runtime_project",
        repo_files=test_case.repo_files,
    )
    seed_file: Path = project_dir / "seed_raw_data.sql"
    import duckdb

    db_path: Path = project_dir / "cursor_runtime.duckdb"
    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    connection.execute(seed_file.read_text(encoding="utf-8"))
    connection.close()

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command, project_dir=project_dir
    )
    assert result.returncode == test_case.expected_exit_code
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout, result.stdout + result.stderr
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in result.stderr, result.stdout + result.stderr
