"""Cleanup of scenarios stopped by an interrupt."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.executor.scenario.classes.scenario_interrupts import ScenarioInterrupts
from sqlbuild.executor.scenario.main._cleanup import execute_scenario_cleanup


def cleanup_interrupted_scenarios(
    *,
    scenario_plans: tuple[ScenarioExecutionPlan, ...],
    adapter: BaseAdapter,
    connection: Any,
    interrupts: ScenarioInterrupts,
) -> None:
    """Drop the relations of interrupted scenarios; a repeat interrupt abandons the rest."""

    if interrupts.abandoned.is_set():
        return
    try:
        scenario_plan: ScenarioExecutionPlan
        for scenario_plan in scenario_plans:
            _ = execute_scenario_cleanup(
                scenario_plan=scenario_plan, adapter=adapter, connection=connection
            )
    except KeyboardInterrupt:
        interrupts.abandon()
        raise
