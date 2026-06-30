"""Local scenario replay entrypoint."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.executor.scenario.helpers.local.execution import (
    execute_local_scenario_load_only_run as _execute_local_scenario_load_only_run,
)
from sqlbuild.executor.scenario.models import ScenarioRunResult


def execute_local_scenario_load_only_run(
    *,
    project_dir: Path,
    scenario_plan: ScenarioExecutionPlan,
    adapter: BaseAdapter,
    strict: bool,
    capture_adapter: str | None = None,
    capture_dialect: str | None = None,
) -> ScenarioRunResult:
    """Run one scenario locally against a run-scoped DuckDB database."""

    return _execute_local_scenario_load_only_run(
        project_dir=project_dir,
        scenario_plan=scenario_plan,
        adapter=adapter,
        strict=strict,
        capture_adapter=capture_adapter,
        capture_dialect=capture_dialect,
    )
