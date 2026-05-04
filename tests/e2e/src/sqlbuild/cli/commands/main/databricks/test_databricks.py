from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.databricks._test_types import (
    DatabricksBuildE2ETestCase,
    DatabricksCliTestCase,
    DatabricksDiffE2ETestCase,
    DatabricksErrorE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.databricks.helpers import (
    cleanup_databricks_schema,
    ensure_databricks_schema_ready,
    execute_databricks_sql,
    fetch_databricks_rows,
    prepare_databricks_diff_project,
    prepare_databricks_query_source,
    prepare_databricks_waffle_shop,
    relation_name,
    write_local_environment_override,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import run_sqb

DATABRICKS_QUERY_E2E_TEST_CASES: list[DatabricksCliTestCase] = [
    DatabricksCliTestCase(
        description="query command uses databricks local override",
        command=("query", "SELECT id AS ID, name AS NAME FROM {source} ORDER BY ID"),
        expected_stdout_fragments=("ID   | 1", "NAME | alice", "ID   | 2", "NAME | bob"),
    ),
    DatabricksCliTestCase(
        description="query command renders json output",
        command=(
            "query",
            "SELECT id AS ID, name AS NAME FROM {source} ORDER BY ID LIMIT 1",
            "--format",
            "json",
        ),
        expected_stdout_fragments=('"ID": 1', '"NAME": "alice"'),
    ),
    DatabricksCliTestCase(
        description="query command renders csv output",
        command=(
            "query",
            "SELECT id AS ID, name AS NAME FROM {source} ORDER BY ID LIMIT 1",
            "--format",
            "csv",
        ),
        expected_stdout_fragments=("ID,NAME", "1,alice"),
    ),
    DatabricksCliTestCase(
        description="query command prints ok for ddl statements",
        command=("query", "CREATE OR REPLACE TABLE {ddl_target} (id INT)"),
        expected_stdout_fragments=("OK",),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    DATABRICKS_QUERY_E2E_TEST_CASES,
    ids=[case.description for case in DATABRICKS_QUERY_E2E_TEST_CASES],
)
def test_given_databricks_local_config_when_running_query_then_outputs_expected_rows(
    tmp_path: Path,
    test_case: DatabricksCliTestCase,
) -> None:
    project_dir: Path
    schema_name: str
    project_dir, schema_name = prepare_databricks_waffle_shop(tmp_path=tmp_path)
    ensure_databricks_schema_ready(schema_name=schema_name)
    source_name: str = prepare_databricks_query_source(schema_name=schema_name)
    ddl_target: str = relation_name(schema_name=schema_name, name="query_target")
    command: tuple[str, ...] = tuple(
        part.format(source=source_name, ddl_target=ddl_target) for part in test_case.command
    )

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(command=command, project_dir=project_dir)

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        fragment: str
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout
    finally:
        cleanup_databricks_schema(schema_name=schema_name)


@pytest.mark.parametrize(
    "test_case",
    [
        DatabricksBuildE2ETestCase(
            description="waffle shop full build succeeds on databricks",
            command=("--no-color", "build", "--concurrency", "4"),
            expected_table_name="fact_orders",
            expected_row_count=10,
            expected_fact_order_rows=(
                (1, "Classic Belgian", "sweet", 1700, "completed", "success"),
                (3, "Chicken and Waffle", "savory", 4350, "completed", "success"),
                (10, "Classic Belgian", "sweet", 3400, "placed", None),
            ),
            expected_daily_revenue_rows=(
                ("2026-04-01", 3, 6, 7100),
                ("2026-04-02", 3, 3, 2550),
                ("2026-04-03", 1, 1, 950),
            ),
            expected_stdout_fragments=("Execution", "OK"),
        )
    ],
    ids=["waffle shop full build succeeds on databricks"],
)
def test_given_waffle_shop_when_running_full_build_on_databricks_then_expected_values_exist(
    tmp_path: Path,
    test_case: DatabricksBuildE2ETestCase,
) -> None:
    project_dir: Path
    schema_name: str
    project_dir, schema_name = prepare_databricks_waffle_shop(tmp_path=tmp_path)

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        fragment: str
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout
        rows: tuple[tuple[object, ...], ...] = fetch_databricks_rows(
            schema_name=schema_name,
            sql=(
                "SELECT COUNT(*) FROM "
                f"{relation_name(schema_name=schema_name, name=test_case.expected_table_name)}"
            ),
        )
        assert rows[0][0] == test_case.expected_row_count
        fact_order_rows: tuple[tuple[object, ...], ...] = fetch_databricks_rows(
            schema_name=schema_name,
            sql=(
                "SELECT order_id, waffle_name, waffle_category, line_total_cents, "
                "order_status, payment_status FROM "
                f"{relation_name(schema_name=schema_name, name='fact_orders')} "
                "WHERE order_id IN (1, 3, 10) ORDER BY order_id"
            ),
        )
        assert fact_order_rows == test_case.expected_fact_order_rows
        daily_revenue_rows: tuple[tuple[object, ...], ...] = fetch_databricks_rows(
            schema_name=schema_name,
            sql=(
                "SELECT CAST(revenue_date AS STRING), order_count, waffles_sold, "
                "total_revenue_cents FROM "
                f"{relation_name(schema_name=schema_name, name='daily_revenue')} "
                "ORDER BY revenue_date"
            ),
        )
        assert daily_revenue_rows == test_case.expected_daily_revenue_rows
    finally:
        cleanup_databricks_schema(schema_name=schema_name)


DATABRICKS_DIFF_E2E_TEST_CASES: list[DatabricksDiffE2ETestCase] = [
    DatabricksDiffE2ETestCase(
        description="schema only diff reports clean identical schemas",
        mutation_sql=(),
        command=(
            "--no-color",
            "diff",
            "--from",
            "prod",
            "--to",
            "dev",
            "--schema-only",
            "--select",
            "stg_orders",
        ),
        expected_stdout_fragments=("stg_orders", "No schema differences."),
        expected_return_code=0,
    ),
    DatabricksDiffE2ETestCase(
        description="full diff reports row mismatch",
        mutation_sql=("UPDATE stg_orders SET amount_cents = amount_cents + 5 WHERE order_id = 1",),
        command=(
            "--no-color",
            "diff",
            "--from",
            "prod",
            "--to",
            "dev",
            "--full",
            "--select",
            "stg_orders",
        ),
        expected_stdout_fragments=("amount_cents", "mismatches=1", "order_id=1 | 100 -> 105"),
        expected_return_code=1,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    DATABRICKS_DIFF_E2E_TEST_CASES,
    ids=[case.description for case in DATABRICKS_DIFF_E2E_TEST_CASES],
)
def test_given_databricks_project_when_running_diff_then_outputs_expected_summary(
    tmp_path: Path,
    test_case: DatabricksDiffE2ETestCase,
) -> None:
    project_dir: Path
    prod_schema: str
    dev_schema: str
    project_dir, prod_schema, dev_schema = prepare_databricks_diff_project(tmp_path=tmp_path)

    try:
        write_local_environment_override(
            project_dir=project_dir,
            environment="prod",
            schema_name=prod_schema,
        )
        prod_build: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"),
            project_dir=project_dir,
        )
        assert prod_build.returncode == 0, prod_build.stdout + prod_build.stderr

        write_local_environment_override(
            project_dir=project_dir,
            environment="dev",
            schema_name=dev_schema,
        )
        dev_build: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"),
            project_dir=project_dir,
        )
        assert dev_build.returncode == 0, dev_build.stdout + dev_build.stderr

        statement: str
        for statement in test_case.mutation_sql:
            execute_databricks_sql(
                schema_name=dev_schema,
                sql=statement.replace(
                    "stg_orders",
                    relation_name(schema_name=dev_schema, name="stg_orders"),
                ),
            )

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        fragment: str
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout
    finally:
        cleanup_databricks_schema(schema_name=prod_schema)
        cleanup_databricks_schema(schema_name=dev_schema)


@pytest.mark.parametrize(
    "test_case",
    [
        DatabricksErrorE2ETestCase(
            description="query preserves underlying error",
            command=("query", "SELECT missing_column FROM (SELECT 1 AS id)"),
            expected_error_fragment="missing_column",
        )
    ],
    ids=["query preserves underlying error"],
)
def test_given_databricks_invalid_query_when_running_query_then_underlying_error_is_preserved(
    tmp_path: Path,
    test_case: DatabricksErrorE2ETestCase,
) -> None:
    project_dir: Path
    schema_name: str
    project_dir, schema_name = prepare_databricks_waffle_shop(tmp_path=tmp_path)
    ensure_databricks_schema_ready(schema_name=schema_name)

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code
        assert test_case.expected_error_fragment in result.stdout + result.stderr
    finally:
        cleanup_databricks_schema(schema_name=schema_name)


@pytest.mark.parametrize(
    "test_case",
    [
        DatabricksErrorE2ETestCase(
            description="build preserves underlying error",
            command=("--no-color", "build", "--select", "databricks_broken_model"),
            expected_error_fragment="missing_column",
        )
    ],
    ids=["build preserves underlying error"],
)
def test_given_databricks_invalid_model_when_building_then_underlying_error_is_preserved(
    tmp_path: Path,
    test_case: DatabricksErrorE2ETestCase,
) -> None:
    project_dir: Path
    schema_name: str
    project_dir, schema_name = prepare_databricks_waffle_shop(tmp_path=tmp_path)
    broken_model: Path = project_dir / "models" / "marts" / "databricks_broken_model.sql"
    broken_model.write_text(
        "MODEL (materialized table);\n\nSELECT missing_column FROM (SELECT 1 AS id)",
        encoding="utf-8",
    )

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code
        assert test_case.expected_error_fragment in result.stdout + result.stderr
    finally:
        cleanup_databricks_schema(schema_name=schema_name)
