"""Public scenario snapshot helper entrypoints."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.executor.scenario.helpers.snapshots import (
    classify_scenario_snapshot_state as _classify_scenario_snapshot_state,
)
from sqlbuild.executor.scenario.models import ScenarioSnapshotStateResult


def classify_scenario_snapshot_state(
    *,
    project_dir: Path,
    scenario_plan: ScenarioExecutionPlan,
    capture_adapter: str | None = None,
    capture_dialect: str | None = None,
) -> ScenarioSnapshotStateResult:
    """Return whether a local scenario snapshot is fresh, missing, stale, or invalid."""

    return _classify_scenario_snapshot_state(
        project_dir=project_dir,
        scenario_plan=scenario_plan,
        capture_adapter=capture_adapter,
        capture_dialect=capture_dialect,
    )
