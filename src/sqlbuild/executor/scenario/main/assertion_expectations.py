"""Scenario assertion expectation execution."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ScenarioAssertionExpectationPlan
from sqlbuild.executor.scenario.models import ScenarioAssertionExpectationExecutionResult
from sqlbuild.executor.types import ExecutionStatus
from sqlbuild.shared.constants import (
    SCENARIO_EXEC_ASSERTION_ERRORED,
    SCENARIO_EXEC_ASSERTION_FAILED,
)


def execute_scenario_assertion_expectation(
    *,
    scenario_name: str,
    expectation: ScenarioAssertionExpectationPlan,
    adapter: BaseAdapter,
    connection: Any,
    sample_limit: int = 10,
) -> ScenarioAssertionExpectationExecutionResult:
    """Execute one scenario assertion; passing assertions return zero rows."""

    try:
        count_cursor: Any = adapter.execute(
            connection=connection,
            sql=f"SELECT COUNT(*) FROM ({expectation.sql}) AS __scenario_assertion_failures",
        )
        count_row: Any | None = count_cursor.fetchone()
        failing_count: int = int(count_row[0]) if count_row is not None else 0
        sample_rows: tuple[tuple[object, ...], ...] = ()
        if failing_count > 0 and sample_limit > 0:
            sample_cursor: Any = adapter.execute(
                connection=connection,
                sql=f"SELECT * FROM ({expectation.sql}) AS __scenario_assertion_failures "
                f"LIMIT {sample_limit}",
            )
            sample_rows = tuple(tuple(row) for row in sample_cursor.fetchall())
    except Exception as exc:
        error_message: str = (
            f"scenario '{scenario_name}' assertion '{expectation.name}' encountered an "
            f"execution error: {exc}"
        )
        return ScenarioAssertionExpectationExecutionResult(
            scenario_name=scenario_name,
            name=expectation.name,
            status=ExecutionStatus.FAILED,
            error_code=SCENARIO_EXEC_ASSERTION_ERRORED,
            error_help=(
                "Inspect the assertion CTE SQL and rerun with --retain to inspect relations."
            ),
            error_message=error_message,
        )

    status: ExecutionStatus = (
        ExecutionStatus.SUCCESS if failing_count == 0 else ExecutionStatus.FAILED
    )
    error_message = None
    if status == ExecutionStatus.FAILED:
        sample_message: str = f"; sample={sample_rows[0]}" if sample_rows else ""
        error_message = (
            f"scenario '{scenario_name}' assertion '{expectation.name}' returned "
            f"{failing_count} failing rows{sample_message}"
        )
    return ScenarioAssertionExpectationExecutionResult(
        scenario_name=scenario_name,
        name=expectation.name,
        status=status,
        failing_row_count=failing_count,
        sample_rows=sample_rows,
        error_code=SCENARIO_EXEC_ASSERTION_FAILED if status == ExecutionStatus.FAILED else None,
        error_help=(
            "Update the scenario data or model logic so the assertion query returns zero rows. "
            "Rerun with --retain to inspect scenario-owned artifacts."
            if status == ExecutionStatus.FAILED
            else None
        ),
        error_message=error_message,
    )
