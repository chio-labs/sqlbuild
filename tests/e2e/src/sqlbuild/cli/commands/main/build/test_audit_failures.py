"""E2E tests for audit failure behavior through the CLI."""

from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    AuditFailureBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    run_sqb,
)

TEST_CASES: list[AuditFailureBuildE2ETestCase] = [
    AuditFailureBuildE2ETestCase(
        description="delta audit failure blocks incremental target update",
        repo_files={
            "sqlbuild_project.yml": dedent(
                """
                name: audit_failure_project
                adapter: duckdb

                connection:
                  database: audit_failures.duckdb

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

                CREATE TABLE IF NOT EXISTS orders (
                  id INTEGER,
                  ordered_at TIMESTAMP,
                  amount_cents INTEGER
                );

                INSERT INTO orders VALUES (1, '2025-12-31 00:30:00', 50);
                """
            ).strip()
            + "\n",
            "models/orders.sql": dedent(
                """
                MODEL (
                  materialized: incremental,
                  incremental_strategy: merge,
                  unique_key: ["id"]
                );

                SELECT id, ordered_at, amount_cents FROM main.raw_orders
                """
            ).strip()
            + "\n",
            "models/schema.yml": dedent(
                """
                models:
                  - name: orders
                    audits:
                      - expression_is_true:
                          name: amount is negative
                          expression: "amount_cents < 0"
                          severity: error
                          run_scope: delta_and_final
                """
            ).strip()
            + "\n",
            "audits/generic/expression_is_true.sql": dedent(
                """
                AUDIT ();

                SELECT * FROM __ref("@model") WHERE NOT (@expression)
                """
            ).strip()
            + "\n",
        },
        command=("--no-color", "build", "--select", "orders"),
        expected_exit_code=1,
        expected_failure_fragment=(
            "delta audit for 'orders' failed before target update with severity level: error"
        ),
        expected_retained_relation_fragment="delta table kept for inspection: main.orders__delta",
    ),
    AuditFailureBuildE2ETestCase(
        description="final audit failure reports target already updated for incremental model",
        repo_files={
            "sqlbuild_project.yml": dedent(
                """
                name: audit_failure_project
                adapter: duckdb

                connection:
                  database: audit_failures.duckdb

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

                CREATE TABLE IF NOT EXISTS orders (
                  id INTEGER,
                  ordered_at TIMESTAMP,
                  amount_cents INTEGER
                );

                INSERT INTO orders VALUES (1, '2025-12-31 00:30:00', 50);
                """
            ).strip()
            + "\n",
            "models/orders.sql": dedent(
                """
                MODEL (
                  materialized: incremental,
                  incremental_strategy: merge,
                  unique_key: ["id"]
                );

                SELECT id, ordered_at, amount_cents FROM main.raw_orders
                """
            ).strip()
            + "\n",
            "models/schema.yml": dedent(
                """
                models:
                  - name: orders
                    audits:
                      - expression_is_true:
                          name: amount is negative
                          expression: "amount_cents < 0"
                          severity: error
                          run_scope: final
                """
            ).strip()
            + "\n",
            "audits/generic/expression_is_true.sql": dedent(
                """
                AUDIT ();

                SELECT * FROM __ref("@model") WHERE NOT (@expression)
                """
            ).strip()
            + "\n",
        },
        command=("--no-color", "build", "--select", "orders"),
        expected_exit_code=1,
        expected_failure_fragment=(
            "final audit for 'orders' failed after target update with severity level: error"
        ),
        expected_retained_relation_fragment="delta table kept for inspection: main.orders__delta",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_audit_failure_projects_when_running_build_then_cli_reports_failure_phase(
    test_case: AuditFailureBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="audit_failure_project",
        repo_files=test_case.repo_files,
    )
    db_path: Path = project_dir / "audit_failures.duckdb"

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    connection.execute((project_dir / "seed_raw_data.sql").read_text(encoding="utf-8"))
    connection.close()

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code
    assert test_case.expected_failure_fragment in result.stdout
    assert test_case.expected_retained_relation_fragment in result.stdout
