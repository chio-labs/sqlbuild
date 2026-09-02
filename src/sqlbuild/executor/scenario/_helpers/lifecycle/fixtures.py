"""Helpers for executing scenario fixture groups."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.compiler.planner.models import ScenarioFixturePlan, SeedPlanEntry
from sqlbuild.executor.build.models import SeedExecutionResult
from sqlbuild.executor.scenario.constants import SCENARIO_EXEC_SEED_FAILED
from sqlbuild.executor.scenario.main._fixtures import execute_scenario_fixture
from sqlbuild.executor.scenario.models import ScenarioFixtureExecutionResult
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.executor.seed.main._execute import execute_seed
from sqlbuild.runtime.observability.classes.resource_attempt_lifecycle import (
    ResourceAttemptLifecycle,
)


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
    scenario_name: str,
    seed_entries: tuple[SeedPlanEntry, ...],
    adapter: BaseAdapter,
    connection: Any,
    run_id: str | None = None,
) -> tuple[SeedExecutionResult, ...]:
    """Load required project seeds into scenario-scoped seed locations."""

    results: list[SeedExecutionResult] = []
    seed_entry: SeedPlanEntry
    for seed_entry in seed_entries:
        with ResourceAttemptLifecycle(
            resource_id=f"scenario:{scenario_name}:seed:{seed_entry.name}",
            resource_kind="seed",
            resource_name=seed_entry.name,
            run_id=run_id,
        ) as lifecycle:
            result: SeedExecutionResult = execute_seed(
                seed_entry=seed_entry,
                adapter=adapter,
                connection=connection,
                statement_recorder=StatementRecorder(),
            )
            if result.status == ExecutionStatus.FAILED:
                error_message: str = result.error_message or "seed load failed"
                result = replace(
                    result,
                    error_code=result.error_code or SCENARIO_EXEC_SEED_FAILED,
                    error_help=(
                        result.error_help
                        or "Check the seed file, schema metadata, and scenario relation target."
                    ),
                    error_message=(
                        f"scenario seed '{seed_entry.name}' failed to load into "
                        "'"
                        f"{seed_entry.destination.qualified_name or seed_entry.destination.name}': "
                        f"{error_message}"
                    ),
                )
                lifecycle.failed(error_code=result.error_code)
        results.append(result)
        if result.status == ExecutionStatus.FAILED:
            break
    return tuple(results)
