"""Public direct source freshness downstream propagation entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.planner.models import PlannerScope
from sqlbuild.compiler.source_freshness._helpers import propagation as propagation_helpers
from sqlbuild.compiler.source_freshness.models import (
    DirectSourceFreshnessPlanningResult,
    DirectSourceFreshnessPropagationResult,
)


def build_direct_source_freshness_propagation_result(
    *,
    source_freshness: DirectSourceFreshnessPlanningResult,
    scope: PlannerScope,
) -> DirectSourceFreshnessPropagationResult:
    """Map changed/unknown source freshness roots to downstream model names."""

    return propagation_helpers.build_direct_source_freshness_propagation_result(
        source_freshness=source_freshness,
        scope=scope,
    )
