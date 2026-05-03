"""SQL unit test execution."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ChainStep, SqlTestPlanEntry
from sqlbuild.executor.testing.models import SqlTestExecutionResult, StepResult
from sqlbuild.executor.testing.types import SqlTestOutcome


def execute_sql_test(
    *,
    test_entry: SqlTestPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
) -> SqlTestExecutionResult:
    """Execute one SQL unit test through its chain steps."""

    step_results: list[StepResult] = []
    overall_outcome: SqlTestOutcome = SqlTestOutcome.PASS

    step: ChainStep
    for step in test_entry.chain:
        step_result: StepResult = _execute_chain_step(
            step=step, adapter=adapter, connection=connection
        )
        step_results.append(step_result)
        if step_result.outcome == SqlTestOutcome.ERROR:
            overall_outcome = SqlTestOutcome.ERROR
            return SqlTestExecutionResult(
                test_name=test_entry.name,
                outcome=overall_outcome,
                step_results=tuple(step_results),
                error_message=f"step '{step.model_name}' encountered an execution error",
            )
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
        error_message=error_message,
    )


def _execute_chain_step(
    *,
    step: ChainStep,
    adapter: BaseAdapter,
    connection: Any,
) -> StepResult:
    """Execute one chain step by comparing actual vs expected results."""

    comparison_sql: str = (
        f"WITH __actual AS ({step.resolved_sql}), "
        f"__expected AS ({step.expected_cte_sql}) "
        f"SELECT "
        f"(SELECT COUNT(*) FROM __actual) AS actual_count, "
        f"(SELECT COUNT(*) FROM __expected) AS expected_count, "
        f"(SELECT COUNT(*) FROM ("
        f"SELECT * FROM __actual EXCEPT SELECT * FROM __expected"
        f")) AS mismatched_count"
    )

    try:
        cursor: Any = adapter.execute(connection, comparison_sql)
        row: Any = cursor.fetchone()
        actual_count: int = int(row[0])
        expected_count: int = int(row[1])
        mismatched_count: int = int(row[2])
    except Exception:
        return StepResult(
            model_name=step.model_name,
            outcome=SqlTestOutcome.ERROR,
        )

    outcome: SqlTestOutcome
    if mismatched_count == 0 and actual_count == expected_count:
        outcome = SqlTestOutcome.PASS
    else:
        outcome = SqlTestOutcome.FAIL

    return StepResult(
        model_name=step.model_name,
        outcome=outcome,
        actual_row_count=actual_count,
        expected_row_count=expected_count,
        mismatched_row_count=mismatched_count,
    )
