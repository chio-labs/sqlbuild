"""E2E tests for sqb test command."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    prepare_waffle_shop,
    run_sqb,
)
from tests.e2e.src.sqlbuild.cli.commands.main.test._test_types import (
    SqlglotChainSqlTestE2ETestCase,
    SqlTestE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.test.helpers import build_chain_test_project_files

SQLGLOT_CHAIN_TEST_CASES: list[SqlglotChainSqlTestE2ETestCase] = [
    SqlglotChainSqlTestE2ETestCase(
        description="sqlglot enabled chain test runs and writes generated ctes",
        sqlglot_enabled=True,
        expected_artifact_fragments=(
            "__source__raw AS (",
            "__ref__stg_orders AS (",
            "__actual__fact_orders AS (",
            "FROM __ref__stg_orders",
            "'US' AS country",
            "' + x + ' AS literal_text",
            "'active' AS status",
            "'fact_orders' AS model_name",
        ),
        unexpected_artifact_fragments=(
            "__actual_0",
            "__actual__fact_orders AS (\n  SELECT\n    id,\n    amount + 1 AS adjusted\n  FROM (",
        ),
    ),
    SqlglotChainSqlTestE2ETestCase(
        description="sqlglot disabled chain test runs and keeps nested fallback sql",
        sqlglot_enabled=False,
        expected_artifact_fragments=(
            "__actual__fact_orders AS (",
            "FROM (",
            "'US' AS country",
            "' + x + ' AS literal_text",
            "'active' AS status",
            "'fact_orders' AS model_name",
        ),
        unexpected_artifact_fragments=(
            "__ref__stg_orders AS (",
            "__actual_0",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    [
        SqlTestE2ETestCase(
            description="test runs SQL unit tests and all pass",
            expected_exit_code=0,
            expected_stdout_fragment="PASS=1",
        ),
    ],
    ids=["test runs SQL unit tests and all pass"],
)
def test_given_waffle_shop_project_when_running_test_then_all_tests_pass(
    test_case: SqlTestE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "test"), project_dir=project_dir
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert test_case.expected_stdout_fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    SQLGLOT_CHAIN_TEST_CASES,
    ids=[case.description for case in SQLGLOT_CHAIN_TEST_CASES],
)
def test_given_chain_sql_test_when_running_test_then_generated_sql_is_valid(
    test_case: SqlglotChainSqlTestE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="chain_test_project",
        repo_files=build_chain_test_project_files(sqlglot_enabled=test_case.sqlglot_enabled),
    )

    test_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "test"), project_dir=project_dir
    )

    assert test_result.returncode == 0, test_result.stdout + test_result.stderr
    assert "PASS=1" in test_result.stdout

    compile_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile"), project_dir=project_dir
    )

    assert compile_result.returncode == 0, compile_result.stdout + compile_result.stderr
    artifact_sql: str = (
        project_dir
        / "target"
        / "compiled"
        / "tests"
        / "_chain_"
        / "fact_orders__stg_orders"
        / "test_chain.sql"
    ).read_text(encoding="utf-8")
    expected_fragment: str
    for expected_fragment in test_case.expected_artifact_fragments:
        assert expected_fragment in artifact_sql
    unexpected_fragment: str
    for unexpected_fragment in test_case.unexpected_artifact_fragments:
        assert unexpected_fragment not in artifact_sql
