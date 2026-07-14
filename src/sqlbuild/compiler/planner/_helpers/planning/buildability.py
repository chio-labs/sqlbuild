"""Selected-scope buildability validation for execution planning."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.planner._helpers.graph.buildability import check_buildability
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import (
    DeferralInputs,
    MissingUpstream,
    PlannerReuseResolution,
    PlannerScopeResolution,
    WarehouseSnapshot,
)


def check_selected_scope_buildability(
    *,
    project: CompiledProject,
    scopes: PlannerScopeResolution,
    snapshot: WarehouseSnapshot,
    deferral: DeferralInputs,
    reuse: PlannerReuseResolution,
) -> None:
    """Raise a planner input error when selected upstream dependencies are missing."""

    external_seed_keys: frozenset[CompiledObjectKey] = frozenset(
        seed.key for seed in project.seeds if seed.external
    )
    missing: tuple[MissingUpstream, ...] = check_buildability(
        selected_keys=scopes.selected_scope.selected_keys,
        upstream_deps=scopes.selected_scope.upstream_deps,
        snapshot=snapshot,
        deferred_relations=deferral.deferred_relations,
        satisfied_keys=reuse.reusable_dependency_baseline_keys | external_seed_keys,
    )
    if missing:
        names: str = ", ".join(m.key.name for m in missing[:5])
        raise PlannerInputError(
            f"cannot build selected scope: {len(missing)} missing upstream dependencies ({names})",
            code="S301",
        )
