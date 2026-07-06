"""Standard reuse resolution phase for execution planning."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.planner.helpers.reuse.standard_reuse_decisions import (
    is_standard_reuse_decision_reusable,
)
from sqlbuild.compiler.planner.helpers.reuse.standard_reuse_planning import (
    build_standard_reuse_planning_result,
)
from sqlbuild.compiler.planner.models import (
    PlannerIdentityContext,
    PlannerOverrides,
    PlannerPolicies,
    PlannerReuseResolution,
    PlannerRuntime,
    PlannerScopeResolution,
    PlannerWarehouseState,
    StandardReuseIdentityInputs,
    StandardReusePlanningResult,
)


def resolve_standard_reuse(
    *,
    runtime: PlannerRuntime,
    scopes: PlannerScopeResolution,
    warehouse: PlannerWarehouseState,
    identities: PlannerIdentityContext,
    overrides: PlannerOverrides,
    policies: PlannerPolicies,
) -> PlannerReuseResolution:
    """Resolve standard reuse decisions and the reusable dependency-baseline keys."""

    standard_reuse: StandardReusePlanningResult | None = (
        build_standard_reuse_planning_result(
            project=runtime.project,
            adapter=runtime.adapter,
            connection=runtime.connection,
            scope=scopes.inspection_scope,
            relations=warehouse.inspection_relations,
            project_config=runtime.project_config,
            local_config=runtime.local_config,
            identity_inputs=StandardReuseIdentityInputs(
                expected_version_hashes=identities.version_identities.model_version_hashes,
                built_fingerprints=warehouse.snapshot.fingerprints.models,
                destination_relation_names=frozenset(warehouse.snapshot.existing_relations),
                cursor_snapshots=warehouse.snapshot.cursor_snapshots,
                custom_prepare_version_materializations=(
                    policies.custom_prepare_version_materializations
                ),
            ),
            full_refresh=overrides.full_refresh,
        )
        if policies.enable_reuse_planning
        else None
    )
    reusable_dependency_baseline_keys: frozenset[CompiledObjectKey] = frozenset(
        key
        for key in scopes.dependency_baseline_candidate_keys
        if standard_reuse is not None
        and standard_reuse.decisions.models.get(key.name) is not None
        and is_standard_reuse_decision_reusable(standard_reuse.decisions.models[key.name].decision)
    )
    return PlannerReuseResolution(
        standard_reuse=standard_reuse,
        dependency_baseline_candidate_keys=scopes.dependency_baseline_candidate_keys,
        reusable_dependency_baseline_keys=reusable_dependency_baseline_keys,
    )
