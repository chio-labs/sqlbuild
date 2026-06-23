"""Public planner entrypoint for run_despite_unchanged planning."""

from __future__ import annotations

from datetime import datetime

from sqlbuild.compiler.planner.helpers.pruning.run_despite_unchanged import (
    build_run_despite_unchanged_planning_result as _build_result,
)
from sqlbuild.compiler.planner.models import PlannerScope, RunDespiteUnchangedPlanningResult
from sqlbuild.compiler.source_freshness.models import StandardSourceFreshnessPlanningResult


def build_run_despite_unchanged_planning_result(
    *,
    scope: PlannerScope,
    source_freshness: StandardSourceFreshnessPlanningResult,
    already_stale_model_names: frozenset[str],
    now: datetime,
) -> RunDespiteUnchangedPlanningResult:
    """Return configured table roots that should run despite unchanged inputs."""

    return _build_result(
        scope=scope,
        source_freshness=source_freshness,
        already_stale_model_names=already_stale_model_names,
        now=now,
    )
