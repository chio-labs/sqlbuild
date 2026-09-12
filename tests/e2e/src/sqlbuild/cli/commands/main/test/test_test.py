"""E2E tests for sqb test command."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.test._test_types import (
    ComplexValuesFixtureE2ETestCase,
    FixtureCompatibilityE2ETestCase,
    ParameterCaseSelectionE2ETestCase,
    PartialFixtureE2ETestCase,
    SqlAnalysisChainSqlTestE2ETestCase,
    SqlTestE2ETestCase,
    SqlTestFixtureValidationE2ETestCase,
    SqlTestInspectConflictE2ETestCase,
    SqlTestPlanInspectionE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.test.helpers import (
    build_assertion_test_project_files,
    build_chain_test_project_files,
    build_complex_values_fixture_project_files,
    build_empty_partial_fixture_project_files,
    build_explicit_typed_null_fixture_project_files,
    build_incompatible_fixture_type_project_files,
    build_invalid_partial_fixture_project_files,
    build_irrelevant_omitted_column_project_files,
    build_macro_test_project_files,
    build_missing_mock_columns_project_files,
    build_mixed_case_partial_fixture_project_files,
    build_mock_boundary_test_project_files,
    build_multiple_invalid_fixtures_project_files,
    build_parameterized_test_project_files,
    build_partial_ref_fixture_project_files,
    build_partial_seed_fixture_project_files,
    build_partial_source_fixture_project_files,
    build_qualified_star_other_relation_project_files,
    build_star_mock_fixture_project_files,
    build_star_partial_fixture_project_files,
    build_transformed_collection_project_files,
    build_unsatisfied_leaf_test_project_files,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    assert_fragments_in_order,
    prepare_inline_project,
    prepare_waffle_shop,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    (
        PartialFixtureE2ETestCase(
            description="known nullable source column receives an implicit typed null",
            repo_files=build_partial_source_fixture_project_files(),
            expected_stdout_fragment="PASS=1",
            expected_artifact_fragments=(
                'CAST(NULL AS TEXT) AS "status"',
                "__sqlbuild_partial_fixture",
            ),
        ),
        PartialFixtureE2ETestCase(
            description="known nullable model-ref column receives an implicit typed null",
            repo_files=build_partial_ref_fixture_project_files(),
            expected_stdout_fragment="PASS=1",
            expected_artifact_fragments=(
                'CAST(NULL AS TEXT) AS "status"',
                "__sqlbuild_partial_fixture",
            ),
        ),
        PartialFixtureE2ETestCase(
            description="known nullable seed column receives an implicit typed null",
            repo_files=build_partial_seed_fixture_project_files(),
            expected_stdout_fragment="PASS=1",
            expected_artifact_fragments=(
                'CAST(NULL AS TEXT) AS "country_name"',
                "__sqlbuild_partial_fixture",
            ),
            artifact_filename="test_countries.sql",
        ),
        PartialFixtureE2ETestCase(
            description="nullable column outside the closure leaves fixture unchanged",
            repo_files=build_irrelevant_omitted_column_project_files(),
            expected_stdout_fragment="PASS=1",
            expected_artifact_fragments=("__source__raw_orders AS (\n  SELECT\n    1 AS order_id",),
            unexpected_artifact_fragments=("__sqlbuild_partial_fixture",),
        ),
        PartialFixtureE2ETestCase(
            description="contracted star closure receives all required nullable columns",
            repo_files=build_star_partial_fixture_project_files(),
            expected_stdout_fragment="PASS=1",
            expected_artifact_fragments=(
                'CAST(NULL AS TEXT) AS "status"',
                "__sqlbuild_partial_fixture",
            ),
        ),
        PartialFixtureE2ETestCase(
            description="zero-row partial fixture preserves emptiness after completion",
            repo_files=build_empty_partial_fixture_project_files(),
            expected_stdout_fragment="PASS=1",
            expected_artifact_fragments=(
                "FALSE",
                'CAST(NULL AS TEXT) AS "status"',
                "__sqlbuild_partial_fixture",
            ),
        ),
        PartialFixtureE2ETestCase(
            description="explicit typed null keeps complete fixture on unchanged path",
            repo_files=build_explicit_typed_null_fixture_project_files(),
            expected_stdout_fragment="PASS=1",
            expected_artifact_fragments=("CAST(NULL AS TEXT) AS status",),
            unexpected_artifact_fragments=("__sqlbuild_partial_fixture",),
        ),
        PartialFixtureE2ETestCase(
            description="qualified star on real relation does not expand mocked relation",
            repo_files=build_qualified_star_other_relation_project_files(),
            expected_stdout_fragment="PASS=1",
            expected_artifact_fragments=("__source__raw_orders AS (",),
            unexpected_artifact_fragments=("__sqlbuild_partial_fixture",),
        ),
        PartialFixtureE2ETestCase(
            description="mixed-case unquoted supplied alias remains referenced through star",
            repo_files=build_mixed_case_partial_fixture_project_files(),
            expected_stdout_fragment="PASS=1",
            expected_artifact_fragments=(
                '"__sqlbuild_partial_fixture".*',
                'CAST(NULL AS TEXT) AS "note"',
            ),
            unexpected_artifact_fragments=('"__sqlbuild_partial_fixture"."Status"',),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_required_nullable_column_omitted_when_testing_then_completes_fixture_implicitly(
    test_case: PartialFixtureE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="partial_fixture_project",
        repo_files=test_case.repo_files,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "test"),
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert test_case.expected_stdout_fragment in result.stdout
    artifacts: tuple[Path, ...] = tuple(
        (project_dir / "target").glob(f"**/{test_case.artifact_filename}")
    )
    assert artifacts
    artifact_sql: str = artifacts[0].read_text(encoding="utf-8")
    for fragment in test_case.expected_artifact_fragments:
        assert fragment in artifact_sql
    for fragment in test_case.unexpected_artifact_fragments:
        assert fragment not in artifact_sql


@pytest.mark.parametrize(
    "test_case",
    [
        SqlTestInspectConflictE2ETestCase(
            description="inspect rejects structured output file",
            expected_exit_code=2,
            expected_stderr_fragment=(
                "test --inspect cannot be combined with --json or --json-output"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_inspection_when_requesting_json_file_then_parser_rejects_conflict(
    test_case: SqlTestInspectConflictE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="inspect_output_conflict_project",
        repo_files=build_parameterized_test_project_files(),
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("test", "--inspect", "--json-output", str(tmp_path / "result.json")),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code
    assert test_case.expected_stderr_fragment in result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        FixtureCompatibilityE2ETestCase(
            description="star mock fixture defers static shape validation",
            repo_files=build_star_mock_fixture_project_files(),
            expected_stdout_fragment="PASS=1",
        ),
        FixtureCompatibilityE2ETestCase(
            description="aggregation output does not inherit scalar input type",
            repo_files=build_transformed_collection_project_files(),
            expected_stdout_fragment="PASS=1",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_valid_fixture_when_static_inference_is_ambiguous_then_test_still_executes(
    test_case: FixtureCompatibilityE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="fixture_compatibility_project",
        repo_files=test_case.repo_files,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "test"),
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert test_case.expected_stdout_fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        ComplexValuesFixtureE2ETestCase(
            description="duckdb executes complex string values",
            adapter_name="duckdb",
            command=("--no-color", "test"),
            expected_stdout_fragment="PASS=1",
        ),
        ComplexValuesFixtureE2ETestCase(
            description="snowflake compiles complex string values unchanged",
            adapter_name="snowflake",
            command=("--no-color", "compile"),
            expected_stdout_fragment="Project compiled",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_complex_strings_in_values_when_processing_then_literals_remain_intact(
    test_case: ComplexValuesFixtureE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="complex_values_project",
        repo_files=build_complex_values_fixture_project_files(adapter_name=test_case.adapter_name),
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert test_case.expected_stdout_fragment in result.stdout
    artifacts: tuple[Path, ...] = tuple((project_dir / "target").glob("**/test_orders.sql"))
    assert artifacts
    artifact_sql: str = artifacts[0].read_text(encoding="utf-8")
    assert "alpha,beta [one] (two)" in artifact_sql
    assert "gamma(delta),[epsilon]" in artifact_sql


@pytest.mark.parametrize(
    "test_case",
    [
        SqlTestFixtureValidationE2ETestCase(
            description="missing source columns are reported together",
            repo_files=build_missing_mock_columns_project_files(),
            expected_stderr_fragments=(
                "tests/unit/test_orders.sql:4",
                "mock source 'raw_orders' is missing required columns: customer_id, status",
                "read by: orders",
            ),
        ),
        SqlTestFixtureValidationE2ETestCase(
            description="required non-nullable source column needs an explicit value",
            repo_files=build_invalid_partial_fixture_project_files(
                status_column_attributes="        type: VARCHAR\n        nullable: false\n"
            ),
            expected_stderr_fragments=("must provide required non-nullable columns: status",),
        ),
        SqlTestFixtureValidationE2ETestCase(
            description="required source column with unknown type is not guessed",
            repo_files=build_invalid_partial_fixture_project_files(
                status_column_attributes="        nullable: true\n"
            ),
            expected_stderr_fragments=(
                "missing required columns: status",
                "types or nullability are not authoritative",
            ),
        ),
        SqlTestFixtureValidationE2ETestCase(
            description="required source column with unknown nullability is not completed",
            repo_files=build_invalid_partial_fixture_project_files(
                status_column_attributes="        type: VARCHAR\n"
            ),
            expected_stderr_fragments=(
                "missing required columns: status",
                "types or nullability are not authoritative",
            ),
        ),
        SqlTestFixtureValidationE2ETestCase(
            description="misspelled supplied source column is rejected for authoritative shape",
            repo_files=build_invalid_partial_fixture_project_files(
                status_column_attributes="        type: VARCHAR\n        nullable: true\n",
                supplied_column="order_identifer",
            ),
            expected_stderr_fragments=(
                "supplies unknown columns: order_identifer",
                "must provide required non-nullable columns: order_id",
            ),
        ),
        SqlTestFixtureValidationE2ETestCase(
            description="duckdb array and scalar types identify the expected column",
            repo_files=build_incompatible_fixture_type_project_files(adapter_name="duckdb"),
            expected_stderr_fragments=(
                "tests/unit/test_orders.sql:5",
                "expected output 'orders' column 'item_ids' has incompatible type VARCHAR",
                "resource type is ARRAY",
                "ARRAY_CONSTRUCT, or PARSE_JSON",
            ),
        ),
        SqlTestFixtureValidationE2ETestCase(
            description="snowflake array and scalar types identify the expected column",
            repo_files=build_incompatible_fixture_type_project_files(adapter_name="snowflake"),
            expected_stderr_fragments=(
                "tests/unit/test_orders.sql:5",
                "expected output 'orders' column 'item_ids' has incompatible type VARCHAR",
                "resource type is ARRAY",
                "ARRAY_CONSTRUCT, or PARSE_JSON",
            ),
        ),
        SqlTestFixtureValidationE2ETestCase(
            description="invalid fixtures are aggregated across selected tests",
            repo_files=build_multiple_invalid_fixtures_project_files(),
            expected_stderr_fragments=(
                "SQL test 'test_orders_a'",
                "tests/unit/test_orders_a.sql:4",
                "missing required columns: customer_id",
                "SQL test 'test_orders_b'",
                "tests/unit/test_orders_b.sql:4",
                "missing required columns: status",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_fixture_when_testing_then_static_diagnostics_prevent_connection(
    test_case: SqlTestFixtureValidationE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="fixture_validation_project",
        repo_files=test_case.repo_files,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "test"),
        project_dir=project_dir,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in result.stderr, result.stdout + result.stderr
    assert "Connecting to" not in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        SqlTestPlanInspectionE2ETestCase(
            description="multi model plan shows real chain",
            repo_files=build_chain_test_project_files(sql_analysis_enabled=True),
            expected_stdout_fragments=(
                "Resolved test plan",
                "mocked sources: raw",
                "real models: stg_orders, fact_orders",
                "expected models: stg_orders, fact_orders",
                "Test plan inspection complete: 1 selected, 0 errors.",
            ),
        ),
        SqlTestPlanInspectionE2ETestCase(
            description="missing leaf mock is reported before execution",
            repo_files=build_unsatisfied_leaf_test_project_files(),
            expected_exit_code=1,
            expected_stdout_fragments=(
                "model 'stg_orders' references __source('raw') which has no mock",
                "model 'fact_orders' references __source('raw') which has no mock",
                "Test plan inspection failed: 1 selected, 2 errors.",
            ),
        ),
        SqlTestPlanInspectionE2ETestCase(
            description="ref mock shows replacement boundary",
            repo_files=build_mock_boundary_test_project_files(),
            expected_stdout_fragments=(
                "mocked refs: stg_orders",
                "real models: int_orders, fact_orders",
                "boundary: stg_orders is replaced by __ref__stg_orders",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_test_when_inspecting_then_fixture_boundaries_and_chain_are_shown(
    test_case: SqlTestPlanInspectionE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="test_plan_inspection_project",
        repo_files=test_case.repo_files,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "test", "--inspect"),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout, result.stdout + result.stderr
    assert "Connecting to" not in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        ParameterCaseSelectionE2ETestCase(
            description="named case runs without sibling cases",
            case_name="open_case",
            expected_exit_code=0,
            expected_stdout_fragments=("Test ready  1 selected", "PASS=1", "open_case"),
        ),
        ParameterCaseSelectionE2ETestCase(
            description="unknown case reports available selected cases",
            case_name="missing_case",
            expected_exit_code=1,
            expected_stderr_fragments=(
                "SQL test case 'missing_case' did not match the selected tests",
                "available cases: closed_case, open_case",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_parameterized_test_when_selecting_case_then_only_named_case_runs(
    test_case: ParameterCaseSelectionE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="parameter_case_project",
        repo_files=build_parameterized_test_project_files(),
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "test",
            "--select",
            "orders",
            "--case",
            test_case.case_name,
        ),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout, result.stdout + result.stderr
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in result.stderr, result.stdout + result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        SqlTestE2ETestCase(
            description="test runs SQL unit tests and all pass",
            expected_exit_code=0,
            expected_stdout_fragment="PASS=5",
            expected_stdout_fragments=(
                "Execution  sqb test  (concurrency: 5)",
                "Connecting to duckdb (5 connections)...",
                "\u2713 Warehouse connected  duckdb",
                "expect  expected stg_orders",
                "expect  expected fact_orders",
                "expect  expected macro calculates_line_total_cents",
                "expect  expected udf detects_completed_orders",
                "expect  expected table_fn returns_customer_orders",
            ),
            expected_ordered_stdout_fragments=(
                "Compiling project...",
                "Compiled project. (<time>)",
                "Execution  sqb test  (concurrency: 5)",
                "Test ready  5 selected, 5 models",
                "Connecting to duckdb (5 connections)...",
                "\u2713 Warehouse connected  duckdb  (<time>)",
                "Preparing test functions...",
                "Prepared test functions. (<time>)",
                "fact_orders",
                "PASS=<n>  FAIL=<n>  TOTAL=<n>",
            ),
        ),
    ],
    ids=lambda case: case.description,
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
        command=("--no-color", "test", "--concurrency", "5"), project_dir=project_dir
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert test_case.expected_stdout_fragment in result.stdout
    expected_fragment: str
    for expected_fragment in test_case.expected_stdout_fragments:
        assert expected_fragment in result.stdout
    assert_fragments_in_order(result.stdout, test_case.expected_ordered_stdout_fragments)
    assert "Inspecting warehouse state..." not in result.stdout
    assert "Generated plan." not in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        SqlAnalysisChainSqlTestE2ETestCase(
            description="sql_analysis enabled chain test runs and writes generated ctes",
            sql_analysis_enabled=True,
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
        SqlAnalysisChainSqlTestE2ETestCase(
            description="sql_analysis disabled chain test runs and keeps nested fallback sql",
            sql_analysis_enabled=False,
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
    ],
    ids=lambda case: case.description,
)
def test_given_chain_sql_test_when_running_test_then_generated_sql_is_valid(
    test_case: SqlAnalysisChainSqlTestE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="chain_test_project",
        repo_files=build_chain_test_project_files(
            sql_analysis_enabled=test_case.sql_analysis_enabled
        ),
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
                "normalizes_status",
                "expect  expected macro normalizes_status",
            ),
        )
    ],
    ids=lambda case: case.description,
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
        / "macro normalizes_status"
        / "normalizes_status.sql"
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
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
