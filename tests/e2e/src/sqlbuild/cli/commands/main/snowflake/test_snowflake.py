from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import run_sqb
from tests.e2e.src.sqlbuild.cli.commands.main.snowflake._test_types import (
    SnowflakeBuildE2ETestCase,
    SnowflakeCliTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.snowflake.helpers import (
    cleanup_snowflake_schema,
    ensure_query_schema_ready,
    fetch_snowflake_rows,
    prepare_snowflake_waffle_shop,
    relation_name,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeCliTestCase(
            description="query command uses snowflake local override",
            command=(
                "query",
                "SELECT CURRENT_DATABASE() AS database_name, CURRENT_SCHEMA() AS schema_name",
            ),
            expected_stdout_fragments=("DATABASE_NAME | SQB_DB", "SCHEMA_NAME   |"),
            expected_schema_fragment="SQLBUILD_E2E_",
        )
    ],
    ids=["query command uses snowflake local override"],
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
