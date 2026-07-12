"""SQL unit test execution."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import SqlTestPlanEntry
from sqlbuild.executor.testing.constants import (
    SQL_TEST_ASSERTION_FAILED_CODE,
    SQL_TEST_EXECUTION_ERROR_CODE,
    SQL_TEST_TOO_LARGE_CODE,
)
from sqlbuild.executor.testing.main.comparison_sql import build_sql_test_comparison_sql
from sqlbuild.executor.testing.main.sql_length import (
    validate_unit_test_sql_length,
)
from sqlbuild.executor.testing.models import SqlTestExecutionResult, StepResult
from sqlbuild.executor.testing.types import SqlTestOutcome


def execute_sql_test(
    *,
    test_entry: SqlTestPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
) -> SqlTestExecutionResult:
    """Execute one SQL unit test as a single comparison query."""

    comparison_sql: str = build_sql_test_comparison_sql(
        test_entry=test_entry,
        set_difference_operator=adapter.render_set_difference_operator(),
        sql_analysis_dialect=adapter.sql_analysis_dialect(),
    )
    error_model_name: str = test_entry.chain[0].model_name if test_entry.chain else test_entry.name
    try:
        validate_unit_test_sql_length(
            sql=comparison_sql,
            adapter=adapter,
            test_name=test_entry.name,
        )
    except Exception:
        error_message: str = (
            f"Combined unit test SQL for '{test_entry.name}' including '{error_model_name}' "
            f"is {len(comparison_sql)} "
            f"characters, which exceeds the recommended maximum of "
            f"{adapter.recommended_max_sql_length()} for this adapter. This test is too "
            "large for a single lightweight unit query. Consider splitting it into smaller "
            "unit tests or moving it to a scenario test."
        )
        return SqlTestExecutionResult(
            test_name=test_entry.name,
            outcome=SqlTestOutcome.ERROR,
            step_results=(
                StepResult(
                    model_name=error_model_name,
                    outcome=SqlTestOutcome.ERROR,
                    error_code=SQL_TEST_TOO_LARGE_CODE,
                    error_message=error_message,
                ),
            ),
            error_code=SQL_TEST_TOO_LARGE_CODE,
            error_message=error_message,
        )

    try:
        cursor: Any = adapter.execute(connection=connection, sql=comparison_sql)
        rows: list[Any] = cursor.fetchall()
    except Exception as error:
        error_message = (
            f"test '{test_entry.name}' encountered an execution error while running "
            f"'{error_model_name}': {error}"
        )
        return SqlTestExecutionResult(
            test_name=test_entry.name,
            outcome=SqlTestOutcome.ERROR,
            step_results=(
                StepResult(
                    model_name=error_model_name,
                    outcome=SqlTestOutcome.ERROR,
                    error_code=SQL_TEST_EXECUTION_ERROR_CODE,
                    error_message=error_message,
                ),
            ),
            error_code=SQL_TEST_EXECUTION_ERROR_CODE,
            error_message=error_message,
        )

    step_results: list[StepResult] = _build_step_results(rows)
    overall_outcome: SqlTestOutcome = SqlTestOutcome.PASS
    step_result: StepResult
    for step_result in step_results:
        if step_result.outcome == SqlTestOutcome.FAIL:
            overall_outcome = SqlTestOutcome.FAIL

    error_message: str | None = None
    if overall_outcome == SqlTestOutcome.FAIL:
        failed_models: list[str] = [
            r.model_name for r in step_results if r.outcome == SqlTestOutcome.FAIL
        ]
        error_message = f"test '{test_entry.name}' failed for models: {', '.join(failed_models)}"

    return SqlTestExecutionResult(
        test_name=test_entry.name,
        outcome=overall_outcome,
        step_results=tuple(step_results),
        error_code=SQL_TEST_ASSERTION_FAILED_CODE
        if overall_outcome == SqlTestOutcome.FAIL
        else None,
        error_message=error_message,
    )


def _build_step_results(rows: list[Any]) -> list[StepResult]:
    """Convert comparison query rows into per-model step results."""

    step_results: list[StepResult] = []
    row: Any
    for row in sorted(rows, key=lambda item: int(item[0])):
        model_name: str = str(row[1])
        actual_count: int = int(row[2])
        expected_count: int = int(row[3])
        mismatched_count: int = int(row[4])
        outcome: SqlTestOutcome
        if mismatched_count == 0 and actual_count == expected_count:
            outcome = SqlTestOutcome.PASS
        else:
            outcome = SqlTestOutcome.FAIL
        step_results.append(
            StepResult(
                model_name=model_name,
                outcome=outcome,
                actual_row_count=actual_count,
                expected_row_count=expected_count,
                mismatched_row_count=mismatched_count,
            )
        )
    return step_results
