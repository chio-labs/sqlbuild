"""Helpers for executing scenario fixture groups."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.planner.models import ScenarioFixturePlan, SeedPlanEntry
from sqlbuild.executor.build.models import SeedExecutionResult
from sqlbuild.executor.scenario.main.fixtures import execute_scenario_fixture
from sqlbuild.executor.scenario.models import ScenarioFixtureExecutionResult
from sqlbuild.executor.seed.main.execute import execute_seed
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


def execute_scenario_seed_entries(
    *,
    seed_entries: tuple[SeedPlanEntry, ...],
    adapter: BaseAdapter,
    connection: Any,
) -> tuple[SeedExecutionResult, ...]:
    """Load required project seeds into scenario-scoped seed targets."""

    results: list[SeedExecutionResult] = []
    seed_entry: SeedPlanEntry
    for seed_entry in seed_entries:
        result: SeedExecutionResult = execute_seed(
            seed_entry=seed_entry,
            adapter=adapter,
            connection=connection,
            statement_recorder=StatementRecorder(),
        )
        results.append(result)
        if result.status == ExecutionStatus.FAILED:
            break
    return tuple(results)
