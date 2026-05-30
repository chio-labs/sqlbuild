"""E2E tests for sqb test command."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    assert_fragments_in_order,
    prepare_inline_project,
    prepare_waffle_shop,
    run_sqb,
)
from tests.e2e.src.sqlbuild.cli.commands.main.test._test_types import (
    SqlglotChainSqlTestE2ETestCase,
    SqlTestE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.test.helpers import (
    build_assertion_test_project_files,
    build_chain_test_project_files,
    build_macro_test_project_files,
)

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
            expected_stdout_fragment="PASS=5",
            expected_stdout_fragments=(
                "Execution  sqb test  (concurrency: 1)",
                "Connecting to duckdb...",
                "Connected to duckdb.",
                "expect  expected stg_orders",
                "expect  expected fact_orders",
                "expect  expected macro calculates line total cents",
                "expect  expected udf detects completed orders",
                "expect  expected table_fn returns customer orders",
            ),
            expected_ordered_stdout_fragments=(
                "Execution  sqb test  (concurrency: 1)",
                "Connecting to duckdb...",
                "Connected to duckdb. (<time>)",
                "Inspecting warehouse state...",
                "Generated plan. (<time>)",
                "Test (5 selected, 5 models)",
                "Connecting to duckdb...",
                "Connected to duckdb. (<time>)",
                "Preparing test functions...",
                "Prepared test functions. (<time>)",
                "fact_orders",
                "PASS=<n>  FAIL=<n>  TOTAL=<n>",
            ),
        ),
    ],
    ids=["test runs SQL unit tests and all pass"],
)
def test_given_waffle_shop_project_when_running_test_then_all_tests_pass(
    test_case: SqlTestE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert build_result.returncode == 0, build_result.stdout + build_result.stderr

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "test"), project_dir=project_dir
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert test_case.expected_stdout_fragment in result.stdout
    expected_fragment: str
    for expected_fragment in test_case.expected_stdout_fragments:
        assert expected_fragment in result.stdout
    assert_fragments_in_order(result.stdout, test_case.expected_ordered_stdout_fragments)


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
    assert "expect  expected stg_orders" in test_result.stdout
    assert "expect  expected fact_orders" in test_result.stdout
    runtime_artifact_sql: str = (
        project_dir
        / "target"
        / "run"
        / "tests"
        / "_chain_"
        / "fact_orders__stg_orders"
        / "test_chain.sql"
    ).read_text(encoding="utf-8")
    expected_runtime_fragment: str
    for expected_runtime_fragment in test_case.expected_artifact_fragments:
        assert expected_runtime_fragment in runtime_artifact_sql

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


@pytest.mark.parametrize(
    "test_case",
    [
        SqlTestE2ETestCase(
            description="macro SQL unit test passes and writes direct comparison artifact",
            expected_exit_code=0,
            expected_stdout_fragment="PASS=1",
            expected_stdout_fragments=(
                "normalizes status",
                "expect  expected macro normalizes status",
            ),
        )
    ],
    ids=["macro SQL unit test passes and writes direct comparison artifact"],
)
def test_given_macro_sql_test_when_running_test_then_actual_and_expected_are_compared(
    test_case: SqlTestE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="macro_test_project",
        repo_files=build_macro_test_project_files(),
    )

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )

    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    assert "PASS=2" in build_result.stdout

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "test"),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert test_case.expected_stdout_fragment in result.stdout
    expected_fragment: str
    for expected_fragment in test_case.expected_stdout_fragments:
        assert expected_fragment in result.stdout
    runtime_artifact_sql: str = (
        project_dir
        / "target"
        / "run"
        / "tests"
        / "macro normalizes status"
        / "normalizes status.sql"
    ).read_text(encoding="utf-8")
    assert "__actual__macro_normalizes_status" in runtime_artifact_sql
    assert "LOWER(TRIM(raw_status)) AS status" in runtime_artifact_sql
    assert "__expected__macro_normalizes_status" in runtime_artifact_sql


@pytest.mark.parametrize(
    "test_case",
    [
        SqlTestE2ETestCase(
            description="assertion-only SQL unit test passes when assertion returns zero rows",
            expected_exit_code=0,
            expected_stdout_fragment="PASS=1",
            expected_stdout_fragments=("orders_assert", "expect  assertion no_negative_orders"),
        )
    ],
    ids=["assertion-only SQL unit test passes when assertion returns zero rows"],
)
def test_given_assertion_only_sql_test_when_assertion_returns_zero_rows_then_it_passes(
    test_case: SqlTestE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="assertion_test_project",
        repo_files=build_assertion_test_project_files(failing=False),
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "test"),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert test_case.expected_stdout_fragment in result.stdout
    expected_fragment: str
    for expected_fragment in test_case.expected_stdout_fragments:
        assert expected_fragment in result.stdout
    runtime_artifact_sql: str = (
        project_dir / "target" / "run" / "tests" / "orders" / "orders_assert.sql"
    ).read_text(encoding="utf-8")
    assert "__assert__no_negative_orders AS" in runtime_artifact_sql
    assert "'assertion no_negative_orders' AS model_name" in runtime_artifact_sql


@pytest.mark.parametrize(
    "test_case",
    [
        SqlTestE2ETestCase(
            description="assertion-only SQL unit test fails when assertion returns rows",
            expected_exit_code=1,
            expected_stdout_fragment="FAIL=1",
            expected_stdout_fragments=(
                "orders_assert",
                "expect  assertion no_negative_orders",
                "FAIL  1 row",
                "test 'orders_assert' failed for models: assertion no_negative_orders",
            ),
        )
    ],
    ids=["assertion-only SQL unit test fails when assertion returns rows"],
)
def test_given_assertion_only_sql_test_when_assertion_returns_rows_then_it_fails(
    test_case: SqlTestE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="failing_assertion_test_project",
        repo_files=build_assertion_test_project_files(failing=True),
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "test"),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert test_case.expected_stdout_fragment in result.stdout
    expected_fragment: str
    for expected_fragment in test_case.expected_stdout_fragments:
        assert expected_fragment in result.stdout
