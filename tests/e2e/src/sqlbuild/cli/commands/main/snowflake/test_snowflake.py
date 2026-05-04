from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import run_sqb
from tests.e2e.src.sqlbuild.cli.commands.main.snowflake._test_types import (
    SnowflakeBuildE2ETestCase,
    SnowflakeCliTestCase,
    SnowflakeDiffE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.snowflake.helpers import (
    cleanup_snowflake_schema,
    ensure_query_schema_ready,
    execute_snowflake_sql,
    fetch_snowflake_rows,
    prepare_snowflake_diff_project,
    prepare_snowflake_waffle_shop,
    relation_name,
    write_local_environment_override,
)

SNOWFLAKE_QUERY_E2E_TEST_CASES: list[SnowflakeCliTestCase] = [
    SnowflakeCliTestCase(
        description="query command uses snowflake local override",
        command=(
            "query",
            "SELECT CURRENT_DATABASE() AS database_name, CURRENT_SCHEMA() AS schema_name",
        ),
        expected_stdout_fragments=("DATABASE_NAME | SQB_DB", "SCHEMA_NAME   |"),
        expected_schema_fragment="SQLBUILD_E2E_",
    ),
    SnowflakeCliTestCase(
        description="query command renders json output",
        command=("query", "SELECT 1 AS id, 'alice' AS name", "--format", "json"),
        expected_stdout_fragments=('"ID": 1', '"NAME": "alice"'),
    ),
    SnowflakeCliTestCase(
        description="query command renders csv output",
        command=("query", "SELECT 1 AS id, 'alice' AS name", "--format", "csv"),
        expected_stdout_fragments=("ID,NAME", "1,alice"),
    ),
    SnowflakeCliTestCase(
        description="query command prints ok for ddl statements",
        command=("query", "CREATE OR REPLACE TEMP TABLE __sqb_query_temp (id INTEGER)"),
        expected_stdout_fragments=("OK",),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SNOWFLAKE_QUERY_E2E_TEST_CASES,
    ids=[case.description for case in SNOWFLAKE_QUERY_E2E_TEST_CASES],
)
def test_given_snowflake_local_config_when_running_query_then_outputs_expected_rows(
    tmp_path: Path,
    test_case: SnowflakeCliTestCase,
) -> None:
    project_dir: Path
    schema_name: str
    project_dir, schema_name = prepare_snowflake_waffle_shop(tmp_path=tmp_path)
    ensure_query_schema_ready(schema_name=schema_name)

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command, project_dir=project_dir
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        fragment: str
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout
        assert test_case.expected_schema_fragment in result.stdout
    finally:
        cleanup_snowflake_schema(schema_name=schema_name)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeBuildE2ETestCase(
            description="waffle shop full build succeeds on snowflake",
            command=("--no-color", "build", "--concurrency", "4"),
            expected_table_name="fact_orders",
            expected_row_count=10,
            expected_stdout_fragments=("Execution", "OK"),
        )
    ],
    ids=["waffle shop full build succeeds on snowflake"],
)
def test_given_waffle_shop_when_running_full_build_on_snowflake_then_expected_table_exists(
    tmp_path: Path,
    test_case: SnowflakeBuildE2ETestCase,
) -> None:
    project_dir: Path
    schema_name: str
    project_dir, schema_name = prepare_snowflake_waffle_shop(tmp_path=tmp_path)

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        fragment: str
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout
        rows: tuple[tuple[object, ...], ...] = fetch_snowflake_rows(
            schema_name=schema_name,
            sql=(
                "SELECT COUNT(*) FROM "
                f"{relation_name(schema_name=schema_name, name=test_case.expected_table_name)}"
            ),
        )
        row_count: object = rows[0][0]
        assert isinstance(row_count, int)
        assert row_count == test_case.expected_row_count
    finally:
        cleanup_snowflake_schema(schema_name=schema_name)


SNOWFLAKE_DIFF_E2E_TEST_CASES: list[SnowflakeDiffE2ETestCase] = [
    SnowflakeDiffE2ETestCase(
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
    SnowflakeDiffE2ETestCase(
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
    SnowflakeDiffE2ETestCase(
        description="verbose diff shows changed row examples",
        mutation_sql=("UPDATE stg_orders SET amount_cents = amount_cents + 5 WHERE order_id = 1",),
        command=(
            "--no-color",
            "diff",
            "--from",
            "prod",
            "--to",
            "dev",
            "--full",
            "--verbose",
            "--select",
            "stg_orders",
        ),
        expected_stdout_fragments=("Examples", "order_id=1 | 100 -> 105"),
        expected_return_code=1,
    ),
    SnowflakeDiffE2ETestCase(
        description="verbose diff shows side only examples",
        mutation_sql=(
            "DELETE FROM stg_orders WHERE order_id = 1",
            "INSERT INTO stg_orders (order_id, customer_id, amount_cents) VALUES (3, 3, 999)",
        ),
        command=(
            "--no-color",
            "diff",
            "--from",
            "prod",
            "--to",
            "dev",
            "--full",
            "--verbose",
            "--select",
            "stg_orders",
        ),
        expected_stdout_fragments=("prod only", "order_id=1", "dev only", "order_id=3"),
        expected_return_code=1,
    ),
    SnowflakeDiffE2ETestCase(
        description="bounded diff reports mismatch inside bounded window",
        mutation_sql=("UPDATE stg_orders SET amount_cents = amount_cents + 5 WHERE order_id = 2",),
        command=(
            "--no-color",
            "diff",
            "--from",
            "prod",
            "--to",
            "dev",
            "--bounded",
            "7d",
            "--select",
            "stg_orders",
        ),
        expected_stdout_fragments=("amount_cents", "mismatches=1", "order_id=2 | 200 -> 205"),
        expected_return_code=1,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SNOWFLAKE_DIFF_E2E_TEST_CASES,
    ids=[case.description for case in SNOWFLAKE_DIFF_E2E_TEST_CASES],
)
def test_given_snowflake_project_when_running_diff_then_outputs_expected_summary(
    tmp_path: Path,
    test_case: SnowflakeDiffE2ETestCase,
) -> None:
    project_dir: Path
    prod_schema: str
    dev_schema: str
    project_dir, prod_schema, dev_schema = prepare_snowflake_diff_project(tmp_path=tmp_path)

    try:
        write_local_environment_override(project_dir=project_dir, environment="prod")
        prod_build: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"),
            project_dir=project_dir,
        )
        assert prod_build.returncode == 0, prod_build.stdout + prod_build.stderr

        write_local_environment_override(project_dir=project_dir, environment="dev")
        dev_build: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"),
            project_dir=project_dir,
        )
        assert dev_build.returncode == 0, dev_build.stdout + dev_build.stderr

        statement: str
        for statement in test_case.mutation_sql:
            execute_snowflake_sql(
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
        cleanup_snowflake_schema(schema_name=prod_schema)
        cleanup_snowflake_schema(schema_name=dev_schema)
