"""Public standard source freshness downstream propagation entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.planner.models import PlannerScope
from sqlbuild.compiler.source_freshness.helpers import propagation as propagation_helpers
from sqlbuild.compiler.source_freshness.models import (
    StandardSourceFreshnessPlanningResult,
    StandardSourceFreshnessPropagationResult,
)


def build_standard_source_freshness_propagation_result(
    *,
    source_freshness: StandardSourceFreshnessPlanningResult,
    scope: PlannerScope,
) -> StandardSourceFreshnessPropagationResult:
    """Map changed/unknown source freshness roots to downstream model names."""

    return propagation_helpers.build_standard_source_freshness_propagation_result(
        source_freshness=source_freshness,
        scope=scope,
    )
