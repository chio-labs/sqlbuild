"""Helpers for executing scenario model groups."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ModelPlanEntry, ScenarioExecutionPlan
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.scenario.main._execute import execute_scenario_model
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.runtime.observability.classes.resource_attempt_lifecycle import (
    ResourceAttemptLifecycle,
)


def execute_scenario_models(
    *,
    scenario_plan: ScenarioExecutionPlan,
    adapter: BaseAdapter,
    connection: Any,
    run_id: str,
) -> tuple[ModelExecutionResult, ...]:
    """Execute scenario model entries in planned dependency order."""

    results: list[ModelExecutionResult] = []
    entry: ModelPlanEntry
    for entry in scenario_plan.model_entries:
        with ResourceAttemptLifecycle(
            resource_id=f"scenario:{scenario_plan.name}:model:{entry.name}",
            resource_kind=str(entry.materialization_type),
            resource_name=entry.name,
            run_id=run_id,
        ) as lifecycle:
            result: ModelExecutionResult = execute_scenario_model(
                scenario_plan=scenario_plan,
                entry=entry,
                adapter=adapter,
                connection=connection,
                run_id=run_id,
            )
            if result.status == ExecutionStatus.FAILED:
                lifecycle.failed(error_code=result.error_code)
        results.append(result)
        if result.status == ExecutionStatus.FAILED:
            break
    return tuple(results)
