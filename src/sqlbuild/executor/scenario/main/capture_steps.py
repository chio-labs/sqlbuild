"""Public scenario snapshot capture steps entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.executor.scenario._helpers.capture.core import execute_scenario_snapshot_capture_steps
from sqlbuild.executor.scenario.models import (
    ScenarioCaptureSettings,
    ScenarioSnapshotCaptureRunResult,
)


def execute_scenario_snapshot_capture_run(
    *,
    project_dir: Path,
    scenario_plan: ScenarioExecutionPlan,
    adapter: BaseAdapter,
    connection: Any,
    settings: ScenarioCaptureSettings,
    local_type_overrides: dict[str, str] | None = None,
) -> ScenarioSnapshotCaptureRunResult:
    """Materialize scenario inputs and capture them for an external entrypoint."""

    return execute_scenario_snapshot_capture_steps(
        project_dir=project_dir,
        scenario_plan=scenario_plan,
        adapter=adapter,
        connection=connection,
        settings=settings,
        local_type_overrides=local_type_overrides,
    )
