"""Helpers for executing scenario expectation groups."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import (
    ScenarioAssertionExpectationPlan,
    ScenarioExecutionPlan,
    ScenarioExpectedExpectationPlan,
)
from sqlbuild.executor.scenario.main.operations.assertion_expectations import (
    execute_scenario_assertion_expectation,
)
from sqlbuild.executor.scenario.main.operations.expected_expectations import (
    execute_scenario_expected_expectation,
)
from sqlbuild.executor.scenario.models import (
    ScenarioAssertionExpectationExecutionResult,
    ScenarioExpectedExpectationExecutionResult,
)


def execute_scenario_expected_expectations(
    *,
    scenario_plan: ScenarioExecutionPlan,
    adapter: BaseAdapter,
    connection: Any,
) -> tuple[ScenarioExpectedExpectationExecutionResult, ...]:
    """Execute expected-output expectations in planned order."""

    results: list[ScenarioExpectedExpectationExecutionResult] = []
    expectation: ScenarioExpectedExpectationPlan
    for expectation in scenario_plan.expected_expectations:
        results.append(
            execute_scenario_expected_expectation(
                scenario_name=scenario_plan.name,
                expectation=expectation,
                adapter=adapter,
                connection=connection,
            )
        )
    return tuple(results)


def execute_scenario_assertion_expectations(
    *,
    scenario_plan: ScenarioExecutionPlan,
    adapter: BaseAdapter,
    connection: Any,
    sample_limit: int = 10,
) -> tuple[ScenarioAssertionExpectationExecutionResult, ...]:
    """Execute zero-row assertion expectations in planned order."""

    results: list[ScenarioAssertionExpectationExecutionResult] = []
    expectation: ScenarioAssertionExpectationPlan
    for expectation in scenario_plan.assertion_expectations:
        results.append(
            execute_scenario_assertion_expectation(
                scenario_name=scenario_plan.name,
                expectation=expectation,
                adapter=adapter,
                connection=connection,
                sample_limit=sample_limit,
            )
        )
    return tuple(results)
