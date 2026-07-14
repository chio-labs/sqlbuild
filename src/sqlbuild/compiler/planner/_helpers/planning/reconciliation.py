"""Write-hash reconciliation phase for execution planning."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.planner._helpers.identity.honest import (
    merge_recomputed_model_changes,
    with_honest_model_write_hashes,
)
from sqlbuild.compiler.planner.models import (
    PlannerChangeReconciliation,
    PlannerChangeResults,
    PlannerIdentityContext,
    PlannerResolvedActions,
    PlannerReuseResolution,
    PlannerScopePruningResult,
    PlannerWarehouseState,
)


def reconcile_execution_changes(
    *,
    warehouse: PlannerWarehouseState,
    identities: PlannerIdentityContext,
    reuse: PlannerReuseResolution,
    pruning: PlannerScopePruningResult,
    changes: PlannerChangeResults,
) -> PlannerChangeReconciliation:
    """Recompute honest write hashes and merge them into resolved actions."""

    baseline_model_hashes: dict[str, str] = {}
    if reuse.standard_reuse is not None:
        key: CompiledObjectKey
        for key in reuse.reusable_dependency_baseline_keys:
            baseline_hash: str | None = reuse.standard_reuse.snapshot.model_snapshots[
                key.name
            ].built_version_hash
            if baseline_hash is not None:
                baseline_model_hashes[key.name] = baseline_hash
    honest_changes: PlannerChangeResults = with_honest_model_write_hashes(
        scope=pruning.execution_scope,
        snapshot=warehouse.snapshot,
        changes=changes,
        version_identities=identities.version_identities,
        available_model_hashes=baseline_model_hashes,
    )
    resolved_actions: PlannerResolvedActions = merge_recomputed_model_changes(
        resolved_actions=pruning.resolved_actions,
        changes=honest_changes,
    )
    return PlannerChangeReconciliation(changes=honest_changes, resolved_actions=resolved_actions)
