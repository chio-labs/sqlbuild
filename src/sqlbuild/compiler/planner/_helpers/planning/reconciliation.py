"""Write-hash reconciliation phase for execution planning."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.identity.honest import (
    merge_recomputed_model_changes,
    with_honest_model_write_hashes,
)
from sqlbuild.compiler.planner.models import (
    PlannerChangeReconciliation,
    PlannerChangeResults,
    PlannerIdentityContext,
    PlannerResolvedActions,
    PlannerScopePruningResult,
    PlannerWarehouseState,
)


def reconcile_execution_changes(
    *,
    warehouse: PlannerWarehouseState,
    identities: PlannerIdentityContext,
    pruning: PlannerScopePruningResult,
    changes: PlannerChangeResults,
) -> PlannerChangeReconciliation:
    """Recompute honest write hashes and merge them into resolved actions."""

    honest_changes: PlannerChangeResults = with_honest_model_write_hashes(
        scope=pruning.execution_scope,
        snapshot=warehouse.snapshot,
        changes=changes,
        version_identities=identities.version_identities,
    )
    resolved_actions: PlannerResolvedActions = merge_recomputed_model_changes(
        resolved_actions=pruning.resolved_actions,
        changes=honest_changes,
    )
    return PlannerChangeReconciliation(changes=honest_changes, resolved_actions=resolved_actions)
