"""Integration tests for snapshot build execution."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from tests.integration.src.sqlbuild.executor.build._test_types import (
    BuildExecutionTestCase,
    SnapshotTimestampExecutionTestCase,
    SnapshotTimestampFailureTestCase,
)
from tests.integration.src.sqlbuild.executor.build.helpers import (
    run_build_for_project,
    verify_model_statuses,
)

_PROJECT_YML: str = (
    'name = "demo"\n'
    'adapter = "duckdb"\n\n'
    "[connection]\n"
    'database = ":memory:"\n\n'
    "[settings]\n"
    'default_audit_severity = "error"\n'
)


SNAPSHOT_TIMESTAMP_TEST_CASES: list[SnapshotTimestampExecutionTestCase] = [
    SnapshotTimestampExecutionTestCase(
        description="current-state timestamp snapshot tracks changed rows",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at\n"
                ");\n\n"
                'SELECT customer_id, plan, updated_at FROM __source("raw_customers")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
        ),
        stale_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2023-12-31 00:00:00' AS updated_at",
        ),
        changed_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'pro' AS plan, "
            "TIMESTAMP '2024-01-03 00:00:00' AS updated_at "
            "UNION ALL SELECT 2 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-02 00:00:00' AS updated_at",
        ),
        expected_query=(
            "SELECT customer_id, plan, CAST(valid_from AS VARCHAR), "
            "CAST(valid_to AS VARCHAR) FROM main.customer_snapshot "
            "ORDER BY customer_id, valid_from"
        ),
        expected_validity_columns=("valid_from", "valid_to"),
        expected_initial_rows=((1, "basic", "2024-01-01 00:00:00", None),),
        expected_stale_rows=((1, "basic", "2024-01-01 00:00:00", None),),
        expected_changed_rows=(
            (1, "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
            (1, "pro", "2024-01-03 00:00:00", None),
            (2, "basic", "2024-01-02 00:00:00", None),
        ),
    ),
    SnapshotTimestampExecutionTestCase(
        description="current-state timestamp snapshot supports composite unique keys",
        model_name="customer_region_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_customer_regions\n"
                "    schema: main\n"
                "    table: raw_customer_regions\n"
            ),
            "models/customer_region_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id, region],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at\n"
                ");\n\n"
                "SELECT customer_id, region, plan, updated_at "
                'FROM __source("raw_customer_regions")'
            ),
        },
        initial_setup_sql=(
            "CREATE TABLE main.raw_customer_regions AS "
            "SELECT 1 AS customer_id, 'us' AS region, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at "
            "UNION ALL SELECT 1 AS customer_id, 'eu' AS region, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
        ),
        stale_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customer_regions AS "
            "SELECT 1 AS customer_id, 'us' AS region, 'stale' AS plan, "
            "TIMESTAMP '2023-12-31 00:00:00' AS updated_at "
            "UNION ALL SELECT 1 AS customer_id, 'eu' AS region, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
        ),
        changed_setup_sql=(
            "CREATE OR REPLACE TABLE main.raw_customer_regions AS "
            "SELECT 1 AS customer_id, 'us' AS region, 'pro' AS plan, "
            "TIMESTAMP '2024-01-03 00:00:00' AS updated_at "
            "UNION ALL SELECT 1 AS customer_id, 'eu' AS region, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
        ),
        expected_query=(
            "SELECT customer_id, region, plan, CAST(valid_from AS VARCHAR), "
            "CAST(valid_to AS VARCHAR) FROM main.customer_region_snapshot "
            "ORDER BY customer_id, region DESC, valid_from"
        ),
        expected_validity_columns=("valid_from", "valid_to"),
        expected_initial_rows=(
            (1, "us", "basic", "2024-01-01 00:00:00", None),
            (1, "eu", "basic", "2024-01-01 00:00:00", None),
        ),
        expected_stale_rows=(
            (1, "us", "basic", "2024-01-01 00:00:00", None),
            (1, "eu", "basic", "2024-01-01 00:00:00", None),
        ),
        expected_changed_rows=(
            (1, "us", "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
            (1, "us", "pro", "2024-01-03 00:00:00", None),
            (1, "eu", "basic", "2024-01-01 00:00:00", None),
        ),
    ),
]

SNAPSHOT_TIMESTAMP_FAILURE_TEST_CASES: list[SnapshotTimestampFailureTestCase] = [
    SnapshotTimestampFailureTestCase(
        description="duplicate source unique key fails before target mutation",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at\n"
                ");\n\n"
                'SELECT customer_id, plan, updated_at FROM __source("raw_customers")'
            ),
        },
        setup_sql=(
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-01 00:00:00' AS updated_at "
            "UNION ALL SELECT 1 AS customer_id, 'pro' AS plan, "
            "TIMESTAMP '2024-01-02 00:00:00' AS updated_at",
        ),
        expected_error_fragment=(
            "source query returned multiple rows for the same unique_key (customer_id)"
        ),
    ),
    SnapshotTimestampFailureTestCase(
        description="validity column collision fails before target mutation",
        model_name="customer_snapshot",
        project_files={
            "sqlbuild_project.toml": _PROJECT_YML,
            "sources/raw.yml": (
                "sources:\n  - name: raw_customers\n    schema: main\n    table: raw_customers\n"
            ),
            "models/customer_snapshot.sql": (
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [customer_id],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at\n"
                ");\n\n"
                "SELECT customer_id, updated_at, updated_at AS valid_from "
                'FROM __source("raw_customers")'
            ),
        },
        setup_sql=(
            "CREATE TABLE main.raw_customers AS "
            "SELECT 1 AS customer_id, TIMESTAMP '2024-01-01 00:00:00' AS updated_at",
        ),
        expected_error_fragment="query output includes generated validity columns: valid_from",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SNAPSHOT_TIMESTAMP_TEST_CASES,
    ids=[case.description for case in SNAPSHOT_TIMESTAMP_TEST_CASES],
)
def test_given_current_state_timestamp_snapshot_when_building_then_tracks_history(
    test_case: SnapshotTimestampExecutionTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)
    build_case: BuildExecutionTestCase = BuildExecutionTestCase(
        description=test_case.description,
        project_files=test_case.project_files,
        setup_sql=test_case.initial_setup_sql,
        expected_status=BuildStatus.SUCCESS,
        expected_success_count=1,
        expected_model_statuses=((test_case.model_name, ExecutionStatus.SUCCESS),),
    )

    initial_result: BuildExecutionResult = run_build_for_project(
        test_case=build_case,
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )
    rows_after_initial: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query).fetchall()
    )
    unchanged_result: BuildExecutionResult = run_build_for_project(
        test_case=BuildExecutionTestCase(
            description=test_case.description,
            project_files=test_case.project_files,
            expected_status=BuildStatus.SUCCESS,
            expected_success_count=1,
            expected_model_statuses=((test_case.model_name, ExecutionStatus.SUCCESS),),
        ),
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )
    rows_after_unchanged: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query).fetchall()
    )
    for sql in test_case.stale_setup_sql:
        connection.execute(sql)
    stale_result: BuildExecutionResult = run_build_for_project(
        test_case=BuildExecutionTestCase(
            description=test_case.description,
            project_files=test_case.project_files,
            expected_status=BuildStatus.SUCCESS,
            expected_success_count=1,
            expected_model_statuses=((test_case.model_name, ExecutionStatus.SUCCESS),),
        ),
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )
    rows_after_stale: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query).fetchall()
    )
    sql: str
    for sql in test_case.changed_setup_sql:
        connection.execute(sql)
    changed_result: BuildExecutionResult = run_build_for_project(
        test_case=BuildExecutionTestCase(
            description=test_case.description,
            project_files=test_case.project_files,
            expected_status=BuildStatus.SUCCESS,
            expected_success_count=1,
            expected_model_statuses=((test_case.model_name, ExecutionStatus.SUCCESS),),
        ),
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )

    assert initial_result.status == BuildStatus.SUCCESS
    assert unchanged_result.status == BuildStatus.SUCCESS
    assert stale_result.status == BuildStatus.SUCCESS
    assert changed_result.status == BuildStatus.SUCCESS
    verify_model_statuses(result=initial_result, test_case=build_case)
    verify_model_statuses(result=unchanged_result, test_case=build_case)
    verify_model_statuses(result=stale_result, test_case=build_case)
    verify_model_statuses(result=changed_result, test_case=build_case)
    validity_columns: tuple[str, ...] = tuple(
        row[0]
        for row in connection.execute(
            "SELECT column_name FROM information_schema.columns "
            f"WHERE table_name = '{test_case.model_name}' "
            "AND column_name IN ('valid_from', 'valid_to') ORDER BY ordinal_position"
        ).fetchall()
    )
    rows_after_changed: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query).fetchall()
    )
    assert validity_columns == test_case.expected_validity_columns
    assert rows_after_initial == test_case.expected_initial_rows
    assert rows_after_unchanged == test_case.expected_initial_rows
    assert rows_after_stale == test_case.expected_stale_rows
    assert rows_after_changed == test_case.expected_changed_rows


@pytest.mark.parametrize(
    "test_case",
    SNAPSHOT_TIMESTAMP_FAILURE_TEST_CASES,
    ids=[case.description for case in SNAPSHOT_TIMESTAMP_FAILURE_TEST_CASES],
)
def test_given_invalid_timestamp_snapshot_source_when_building_then_fails_before_target_mutation(
    test_case: SnapshotTimestampFailureTestCase,
    tmp_path: Path,
    write_repo_files: Callable[[Path, dict[str, str]], None],
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    write_repo_files(tmp_path, test_case.project_files)

    result: BuildExecutionResult = run_build_for_project(
        test_case=BuildExecutionTestCase(
            description=test_case.description,
            project_files=test_case.project_files,
            setup_sql=test_case.setup_sql,
            expected_status=BuildStatus.FAILED,
            expected_failure_count=1,
            expected_model_statuses=((test_case.model_name, ExecutionStatus.FAILED),),
        ),
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )

    assert result.status == BuildStatus.FAILED
    assert result.failure_count == 1
    verify_model_statuses(
        result=result,
        test_case=BuildExecutionTestCase(
            description=test_case.description,
            project_files=test_case.project_files,
            expected_status=BuildStatus.FAILED,
            expected_model_statuses=((test_case.model_name, ExecutionStatus.FAILED),),
        ),
    )
    assert test_case.expected_error_fragment in (result.model_results[0].error_message or "")
    target_exists: bool = (
        connection.execute(
            f"SELECT 1 FROM information_schema.tables WHERE table_name = '{test_case.model_name}'"
        ).fetchone()
        is not None
    )
    assert target_exists is False
