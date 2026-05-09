"""Helpers for executing scenario fixture groups."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ScenarioFixturePlan
from sqlbuild.executor.scenario.main.fixtures import execute_scenario_fixture
from sqlbuild.executor.scenario.models import ScenarioFixtureExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus


def execute_scenario_fixtures(
    *,
    scenario_name: str,
    fixture_plans: tuple[ScenarioFixturePlan, ...],
    adapter: BaseAdapter,
    connection: Any,
) -> tuple[ScenarioFixtureExecutionResult, ...]:
    """Materialize scenario fixtures in planned order."""

    results: list[ScenarioFixtureExecutionResult] = []
    fixture_plan: ScenarioFixturePlan
    for fixture_plan in fixture_plans:
        result: ScenarioFixtureExecutionResult = execute_scenario_fixture(
            scenario_name=scenario_name,
            fixture_plan=fixture_plan,
            adapter=adapter,
            connection=connection,
        )
        results.append(result)
        if result.status == ExecutionStatus.FAILED:
            break
    return tuple(results)
