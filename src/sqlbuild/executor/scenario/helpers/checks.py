"""Helpers for executing scenario check groups."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import (
    ScenarioAssertionCheckPlan,
    ScenarioExecutionPlan,
    ScenarioExpectedCheckPlan,
)
from sqlbuild.executor.scenario.main.assertion_checks import execute_scenario_assertion_check
from sqlbuild.executor.scenario.main.expected_checks import execute_scenario_expected_check
from sqlbuild.executor.scenario.models import (
    ScenarioAssertionCheckExecutionResult,
    ScenarioExpectedCheckExecutionResult,
)


def execute_scenario_expected_checks(
    *,
    scenario_plan: ScenarioExecutionPlan,
    adapter: BaseAdapter,
    connection: Any,
) -> tuple[ScenarioExpectedCheckExecutionResult, ...]:
    """Execute expected-output checks in planned order."""

    results: list[ScenarioExpectedCheckExecutionResult] = []
    check: ScenarioExpectedCheckPlan
    for check in scenario_plan.expected_checks:
        results.append(
            execute_scenario_expected_check(
                scenario_name=scenario_plan.name,
                check=check,
                adapter=adapter,
                connection=connection,
            )
        )
    return tuple(results)


def execute_scenario_assertion_checks(
    *,
    scenario_plan: ScenarioExecutionPlan,
    adapter: BaseAdapter,
    connection: Any,
    sample_limit: int = 10,
) -> tuple[ScenarioAssertionCheckExecutionResult, ...]:
    """Execute zero-row assertion checks in planned order."""

    results: list[ScenarioAssertionCheckExecutionResult] = []
    check: ScenarioAssertionCheckPlan
    for check in scenario_plan.assertion_checks:
        results.append(
            execute_scenario_assertion_check(
                scenario_name=scenario_plan.name,
                check=check,
                adapter=adapter,
                connection=connection,
                sample_limit=sample_limit,
            )
        )
    return tuple(results)
