"""Test helpers for build executor integration tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.shared.types import TablePromotionMode
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.operations.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.build.main.execute import execute_build_plan
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus
from tests.integration.src.sqlbuild.executor.build._test_types import (
    BuildExecutionTestCase,
)


def run_build_for_project(
    *,
    test_case: BuildExecutionTestCase,
    project_dir: Path,
    adapter: DuckDbAdapter,
    connection: Any,
) -> BuildExecutionResult:
    """Discover, compile, plan, then execute a build for a fake project."""

    sql: str
    for sql in test_case.setup_sql:
        connection.execute(sql)

    discovered: DiscoveredProjectInputs = discover_project_inputs(project_dir=project_dir)
    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered,
        adapter=adapter,
        no_sql_validation=True,
    )
    plan: PlanOutput = pipeline_result.plan_output

    settings_mode: str | None = discovered.project_config.settings.table_promotion_mode
    promotion_mode: TablePromotionMode = (
        TablePromotionMode(settings_mode)
        if settings_mode
        else TablePromotionMode(adapter.default_table_promotion_mode())
    )

    return execute_build_plan(
        plan=plan,
        adapter=adapter,
        connection_config={"database": str(project_dir / "test.duckdb")},
        connections=(connection,),
        scheduler_connection=connection,
        promotion_mode=promotion_mode,
        run_id="test_run",
        query_change_tracking=test_case.query_change_tracking,
        snapshots=discovered.project_config.snapshots,
        allow_snapshot_schema_change=test_case.allow_snapshot_schema_change,
        run_audits=test_case.run_audits,
        run_tests=test_case.run_tests,
        fail_fast=test_case.fail_fast,
    )


def verify_model_statuses(
    *,
    result: BuildExecutionResult,
    test_case: BuildExecutionTestCase,
) -> None:
    """Assert per-model execution statuses match expected."""

    if not test_case.expected_model_statuses:
        return
    actual_statuses: dict[str, ExecutionStatus] = {
        r.model_name: r.status for r in result.model_results
    }
    expected_name: str
    expected_status: ExecutionStatus
    for expected_name, expected_status in test_case.expected_model_statuses:
        assert actual_statuses.get(expected_name) == expected_status

    actual_errors: dict[str, str] = {
        r.model_name: r.error_message or "" for r in result.model_results
    }
    expected_fragment: str
    for expected_name, expected_fragment in test_case.expected_model_error_fragments:
        assert expected_fragment in actual_errors.get(expected_name, "")

    actual_error_codes: dict[str, str | None] = {
        r.model_name: r.error_code for r in result.model_results
    }
    expected_code: str
    for expected_name, expected_code in test_case.expected_model_error_codes:
        assert actual_error_codes.get(expected_name) == expected_code


def verify_function_statuses(
    *,
    result: BuildExecutionResult,
    test_case: BuildExecutionTestCase,
) -> None:
    """Assert per-function execution statuses and error fragments match expected."""

    if (
        not test_case.expected_function_statuses
        and not test_case.expected_function_error_fragments
        and not test_case.expected_function_error_codes
    ):
        return
    actual_statuses: dict[str, ExecutionStatus] = {
        r.function_name: r.status for r in result.function_results
    }
    expected_name: str
    expected_status: ExecutionStatus
    for expected_name, expected_status in test_case.expected_function_statuses:
        assert actual_statuses.get(expected_name) == expected_status

    actual_errors: dict[str, str] = {
        r.function_name: r.error_message or "" for r in result.function_results
    }
    expected_fragment: str
    for expected_name, expected_fragment in test_case.expected_function_error_fragments:
        assert expected_fragment in actual_errors.get(expected_name, "")

    actual_error_codes: dict[str, str | None] = {
        r.function_name: r.error_code for r in result.function_results
    }
    expected_code: str
    for expected_name, expected_code in test_case.expected_function_error_codes:
        assert actual_error_codes.get(expected_name) == expected_code


def verify_test_counts(
    *,
    result: BuildExecutionResult,
    test_case: BuildExecutionTestCase,
) -> None:
    """Assert test result counts match expected."""

    assert len(result.test_results) == test_case.expected_test_count

    actual_error_codes: dict[str, str | None] = {
        r.test_name: r.error_code for r in result.test_results
    }
    expected_code: str
    for expected_name, expected_code in test_case.expected_test_error_codes:
        assert actual_error_codes.get(expected_name) == expected_code


def verify_audit_counts(
    *,
    result: BuildExecutionResult,
    test_case: BuildExecutionTestCase,
) -> None:
    """Assert audit result counts match expected."""

    total_model_audits: int = sum(len(r.audit_results) for r in result.model_results)
    assert total_model_audits == test_case.expected_model_audit_count
    assert len(result.source_audit_results) == test_case.expected_source_audit_count
    assert len(result.end_audit_results) == test_case.expected_end_audit_count
    assert result.warning_count == test_case.expected_warning_count


def verify_warehouse_state(
    *,
    connection: Any,
    test_case: BuildExecutionTestCase,
) -> None:
    """Assert actual warehouse state matches expected queries and missing relations."""

    query: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query, expected_rows in test_case.expected_query_results:
        cursor: Any = connection.execute(query)
        actual_rows: tuple[tuple[object, ...], ...] = tuple(tuple(row) for row in cursor.fetchall())
        assert actual_rows == expected_rows, (
            f"Query: {query}\nExpected: {expected_rows}\nActual: {actual_rows}"
        )

    relation: str
    for relation in test_case.expected_missing_relations:
        parts: list[str] = relation.split(".")
        schema: str | None = parts[0] if len(parts) > 1 else None
        name: str = parts[-1]
        cursor = connection.execute(
            "SELECT 1 FROM information_schema.tables "
            f"WHERE table_name = '{name}'" + (f" AND table_schema = '{schema}'" if schema else "")
        )
        assert cursor.fetchone() is None, f"Relation {relation} should not exist but was found"
