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


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotTimestampExecutionTestCase(
            description="current-state timestamp snapshot tracks changed rows",
            project_files={
                "sqlbuild_project.toml": _PROJECT_YML,
                "sources/raw.yml": (
                    "sources:\n"
                    "  - name: raw_customers\n"
                    "    schema: main\n"
                    "    table: raw_customers\n"
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
            expected_initial_rows=((1, "basic", "2024-01-01 00:00:00", None),),
            expected_changed_rows=(
                (1, "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
                (1, "pro", "2024-01-03 00:00:00", None),
                (2, "basic", "2024-01-02 00:00:00", None),
            ),
        )
    ],
    ids=["current-state timestamp snapshot tracks changed rows"],
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
        expected_model_statuses=(("customer_snapshot", ExecutionStatus.SUCCESS),),
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
            expected_model_statuses=(("customer_snapshot", ExecutionStatus.SUCCESS),),
        ),
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )
    rows_after_unchanged: tuple[tuple[object, ...], ...] = tuple(
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
            expected_model_statuses=(("customer_snapshot", ExecutionStatus.SUCCESS),),
        ),
        project_dir=tmp_path,
        adapter=adapter,
        connection=connection,
    )

    assert initial_result.status == BuildStatus.SUCCESS
    assert unchanged_result.status == BuildStatus.SUCCESS
    assert changed_result.status == BuildStatus.SUCCESS
    verify_model_statuses(result=initial_result, test_case=build_case)
    verify_model_statuses(result=unchanged_result, test_case=build_case)
    verify_model_statuses(result=changed_result, test_case=build_case)
    rows_after_changed: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in connection.execute(test_case.expected_query).fetchall()
    )
    assert rows_after_initial == test_case.expected_initial_rows
    assert rows_after_unchanged == test_case.expected_initial_rows
    assert rows_after_changed == test_case.expected_changed_rows
