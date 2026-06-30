"""Scenario expected-output expectation execution."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ScenarioExpectedExpectationPlan
from sqlbuild.executor.scenario.main.expected_comparison_sql import (
    build_scenario_expected_comparison_sql,
)
from sqlbuild.executor.scenario.models import ScenarioExpectedExpectationExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.shared.constants import (
    SCENARIO_EXEC_EXPECTED_ERRORED,
    SCENARIO_EXEC_EXPECTED_FAILED,
    SCENARIO_EXEC_EXPECTED_INTERNAL,
)
from sqlbuild.shared.helpers.naming import resolve_relation_location_qualified_name


def execute_scenario_expected_expectation(
    *,
    scenario_name: str,
    expectation: ScenarioExpectedExpectationPlan,
    adapter: BaseAdapter,
    connection: Any,
) -> ScenarioExpectedExpectationExecutionResult:
    """Compare one scenario-built model relation with its expected query."""

    actual_relation: str = resolve_relation_location_qualified_name(
        adapter=adapter, location=expectation.actual_destination
    )
    comparison_sql: str = build_scenario_expected_comparison_sql(
        actual_sql=f"SELECT * FROM {actual_relation}",
        expected_sql=expectation.expected_sql,
        set_difference_operator=adapter.render_set_difference_operator(),
    )
    try:
        cursor: Any = adapter.execute(connection, comparison_sql)
        row: Any | None = cursor.fetchone()
    except Exception as exc:
        error_message: str = (
            f"scenario '{scenario_name}' expected comparison for model "
            f"'{expectation.model_name}' encountered an execution error: {exc}"
        )
        return ScenarioExpectedExpectationExecutionResult(
            scenario_name=scenario_name,
            model_name=expectation.model_name,
            status=ExecutionStatus.FAILED,
            error_code=SCENARIO_EXEC_EXPECTED_ERRORED,
            error_help="Inspect the expected CTE SQL and rerun with --retain to inspect relations.",
            error_message=error_message,
        )

    if row is None:
        return ScenarioExpectedExpectationExecutionResult(
            scenario_name=scenario_name,
            model_name=expectation.model_name,
            status=ExecutionStatus.FAILED,
            error_code=SCENARIO_EXEC_EXPECTED_INTERNAL,
            error_help=(
                "This is likely a SQLBuild bug. Please file an issue with the scenario name."
            ),
            error_message=(
                f"scenario '{scenario_name}' expected comparison for model "
                f"'{expectation.model_name}' returned no comparison row"
            ),
        )

    actual_count: int = int(row[0])
    expected_count: int = int(row[1])
    mismatched_count: int = int(row[2])
    status: ExecutionStatus = (
        ExecutionStatus.SUCCESS
        if mismatched_count == 0 and actual_count == expected_count
        else ExecutionStatus.FAILED
    )
    error_message = None
    if status == ExecutionStatus.FAILED:
        error_message = (
            f"scenario '{scenario_name}' expected comparison for model "
            f"'{expectation.model_name}' failed: "
            f"actual={actual_count} expected={expected_count} mismatched={mismatched_count}"
        )
    return ScenarioExpectedExpectationExecutionResult(
        scenario_name=scenario_name,
        model_name=expectation.model_name,
        status=status,
        actual_row_count=actual_count,
        expected_row_count=expected_count,
        mismatched_row_count=mismatched_count,
        error_code=SCENARIO_EXEC_EXPECTED_FAILED if status == ExecutionStatus.FAILED else None,
        error_help=(
            "Compare the expected CTE with the retained scenario model relation. "
            "Rerun with --retain to inspect scenario-owned artifacts."
            if status == ExecutionStatus.FAILED
            else None
        ),
        error_message=error_message,
    )
