"""Public scenario executor entry point."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.executor.scenario._helpers.execution.run import execute_scenario_run_steps
from sqlbuild.executor.scenario.models import ScenarioRunResult


def execute_scenario_run(
    *,
    scenario_plan: ScenarioExecutionPlan,
    adapter: BaseAdapter,
    connection: Any,
    run_id: str,
    retain: bool,
) -> ScenarioRunResult:
    """Execute a planned scenario for an external entrypoint."""

    return execute_scenario_run_steps(
        scenario_plan=scenario_plan,
        adapter=adapter,
        connection=connection,
        run_id=run_id,
        retain=retain,
    )
