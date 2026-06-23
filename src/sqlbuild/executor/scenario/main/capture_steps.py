"""Public scenario snapshot capture steps entry point."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.executor.scenario.helpers.capture.core import execute_scenario_snapshot_capture_steps
from sqlbuild.executor.scenario.models import (
    ScenarioSnapshotCaptureLimits,
    ScenarioSnapshotCaptureRunResult,
)


def execute_scenario_snapshot_capture_run(
    *,
    project_dir: Path,
    scenario_plan: ScenarioExecutionPlan,
    adapter: BaseAdapter,
    connection: Any,
    captured_at: str,
    capture_adapter: str,
    capture_dialect: str,
    sqlbuild_version: str,
    retain: bool,
    local_type_overrides: dict[str, str] | None = None,
    limits: ScenarioSnapshotCaptureLimits | None = None,
) -> ScenarioSnapshotCaptureRunResult:
    """Materialize scenario inputs and capture them for an external entrypoint."""

    return execute_scenario_snapshot_capture_steps(
        project_dir=project_dir,
        scenario_plan=scenario_plan,
        adapter=adapter,
        connection=connection,
        captured_at=captured_at,
        capture_adapter=capture_adapter,
        capture_dialect=capture_dialect,
        sqlbuild_version=sqlbuild_version,
        retain=retain,
        local_type_overrides=local_type_overrides,
        limits=limits,
    )
