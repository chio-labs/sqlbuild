"""Selected-scope buildability validation for execution planning."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.planner._helpers.graph.buildability import (
    check_buildability,
    missing_upstream_message,
)
from sqlbuild.compiler.planner._helpers.graph.core import build_execution_edge_origins
from sqlbuild.compiler.planner._helpers.warehouse.source_tables import (
    check_selected_source_tables_exist,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import (
    DeferralInputs,
    MissingUpstream,
    PlannerRuntime,
    PlannerScopeResolution,
    PlannerWarehouseState,
    WarehouseSnapshot,
)


def check_selected_scope_buildability(
    *,
    runtime: PlannerRuntime,
    scopes: PlannerScopeResolution,
    warehouse: PlannerWarehouseState,
    deferral: DeferralInputs,
) -> None:
    """Raise a planner input error when selected upstream inputs are missing."""

    project: CompiledProject = runtime.project
    snapshot: WarehouseSnapshot = warehouse.snapshot
    external_seed_keys: frozenset[CompiledObjectKey] = frozenset(
        seed.key for seed in project.seeds if seed.external
    )
    missing: tuple[MissingUpstream, ...] = check_buildability(
        selected_keys=scopes.selected_scope.selected_keys,
        upstream_deps=scopes.selected_scope.upstream_deps,
        snapshot=snapshot,
        deferred_relations=deferral.deferred_relations,
        satisfied_keys=external_seed_keys,
    )
    if missing:
        raise PlannerInputError(
            missing_upstream_message(
                missing=missing, edge_origins=build_execution_edge_origins(project)
            ),
            code="S301",
        )
    check_selected_source_tables_exist(
        project=project,
        adapter=runtime.adapter,
        connection=runtime.connection,
        scope=scopes.selected_scope,
        relations=warehouse.inspection_relations,
    )
