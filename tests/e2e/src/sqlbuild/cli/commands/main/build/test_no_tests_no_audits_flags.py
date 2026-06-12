from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    run_sqb,
)


def test_given_build_no_tests_when_building_then_skips_sql_tests_but_runs_audits(
    tmp_path: Path,
) -> None:
    project_dir: Path = _prepare_project(tmp_path=tmp_path, project_name="build_no_tests_project")

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--no-tests"),
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "test      test_orders" not in result.stdout
    assert "audit     not_null" in result.stdout


def test_given_build_no_audits_when_building_then_skips_audits_but_runs_sql_tests(
    tmp_path: Path,
) -> None:
    project_dir: Path = _prepare_project(tmp_path=tmp_path, project_name="build_no_audits_project")

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--no-audits"),
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "test      test_orders" in result.stdout
    assert "audit     not_null" not in result.stdout


def _prepare_project(*, tmp_path: Path, project_name: str) -> Path:
    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": dedent(
                f"""
                name = "{project_name}"
                adapter = "duckdb"

                [connection]
                database = "warehouse.duckdb"
                """
            ).strip()
            + "\n",
            "models/orders.sql": dedent(
                """
                MODEL (
                  materialized table,
                  columns (order_id (audits [not_null])),
                );

                SELECT 1 AS order_id
                """
            ).strip()
            + "\n",
            "tests/unit/test_orders.sql": dedent(
                """
                TEST();

                WITH
                __ref__orders AS (SELECT 1 AS order_id),
                __expected__orders AS (SELECT 1 AS order_id)
                SELECT 1
                """
            ).strip()
            + "\n",
        },
    )
