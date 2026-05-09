"""Scenario assertion check execution."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ScenarioAssertionCheckPlan
from sqlbuild.executor.scenario.models import ScenarioAssertionCheckExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus


def execute_scenario_assertion_check(
    *,
    scenario_name: str,
    check: ScenarioAssertionCheckPlan,
    adapter: BaseAdapter,
    connection: Any,
    sample_limit: int = 10,
) -> ScenarioAssertionCheckExecutionResult:
    """Execute one scenario assertion; passing assertions return zero rows."""

    try:
        count_cursor: Any = adapter.execute(
            connection,
            f"SELECT COUNT(*) FROM ({check.sql}) AS __scenario_assertion_failures",
        )
        count_row: Any | None = count_cursor.fetchone()
        failing_count: int = int(count_row[0]) if count_row is not None else 0
        sample_rows: tuple[tuple[object, ...], ...] = ()
        if failing_count > 0 and sample_limit > 0:
            sample_cursor: Any = adapter.execute(
                connection,
                f"SELECT * FROM ({check.sql}) AS __scenario_assertion_failures "
                f"LIMIT {sample_limit}",
            )
            sample_rows = tuple(tuple(row) for row in sample_cursor.fetchall())
    except Exception as exc:
        error_message: str = (
            f"scenario '{scenario_name}' assertion '{check.name}' encountered an "
            f"execution error: {exc}"
        )
        return ScenarioAssertionCheckExecutionResult(
            scenario_name=scenario_name,
            name=check.name,
            status=ExecutionStatus.FAILED,
            error_message=error_message,
        )

    status: ExecutionStatus = (
        ExecutionStatus.SUCCESS if failing_count == 0 else ExecutionStatus.FAILED
    )
    error_message = None
    if status == ExecutionStatus.FAILED:
        error_message = (
            f"scenario '{scenario_name}' assertion '{check.name}' returned "
            f"{failing_count} failing rows"
        )
    return ScenarioAssertionCheckExecutionResult(
        scenario_name=scenario_name,
        name=check.name,
        status=status,
        failing_row_count=failing_count,
        sample_rows=sample_rows,
        error_message=error_message,
    )
