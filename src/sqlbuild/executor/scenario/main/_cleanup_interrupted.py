"""Drop the relations of scenarios stopped by an interrupt."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.executor.scenario._helpers.execution.interrupts import (
    cleanup_interrupted_scenarios as _cleanup_interrupted_scenarios,
)
from sqlbuild.executor.scenario.classes.scenario_interrupts import ScenarioInterrupts


def cleanup_interrupted_scenarios(
    *,
    scenario_plans: tuple[ScenarioExecutionPlan, ...],
    adapter: BaseAdapter,
    connection: Any,
    interrupts: ScenarioInterrupts,
) -> None:
    """Drop interrupted scenarios' relations; a repeat interrupt skips the rest."""

    return _cleanup_interrupted_scenarios(
        scenario_plans=scenario_plans,
        adapter=adapter,
        connection=connection,
        interrupts=interrupts,
    )
