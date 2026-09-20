"""Version identity and stale-warning change phases for execution planning."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner._helpers.changes.detect import detect_model_changes_in_scope
from sqlbuild.compiler.planner._helpers.identity.direct import (
    build_direct_model_version_identities,
)
from sqlbuild.compiler.planner.models import (
    ChangeDetectionResult,
    DirectModelVersionIdentities,
    PlannerChangeResults,
    PlannerIdentityContext,
    PlannerScopeResolution,
    WarehouseSnapshot,
)


def build_planner_identity_context(
    *,
    project: CompiledProject,
    scopes: PlannerScopeResolution,
    include_stale_warning_identities: bool = True,
) -> PlannerIdentityContext:
    """Build expected version identities for the inspection and stale-warning scopes."""

    version_identities: DirectModelVersionIdentities = build_direct_model_version_identities(
        functions=project.functions,
        seeds=project.seeds,
        scope=scopes.inspection_scope,
        hook_functions=project.hook_functions,
    )
    return PlannerIdentityContext(
        version_identities=version_identities,
        stale_warning_identities=(
            build_direct_model_version_identities(
                functions=project.functions,
                seeds=project.seeds,
                scope=scopes.stale_warning_scope,
                hook_functions=project.hook_functions,
            )
            if include_stale_warning_identities
            else version_identities
        ),
    )


def detect_stale_warning_changes(
    *,
    project: CompiledProject,
    scopes: PlannerScopeResolution,
    snapshot: WarehouseSnapshot,
    identities: PlannerIdentityContext,
    execution_changes: PlannerChangeResults,
) -> PlannerChangeResults:
    """Detect only stale-warning model changes not already known from execution planning."""

    reusable_model_names: frozenset[str] = _reusable_execution_model_names(
        identities=identities,
        execution_changes=execution_changes,
        query_change_tracking=project.settings.query_change_tracking,
    )
    stale_keys: frozenset[CompiledObjectKey] = frozenset(
        scopes.stale_warning_scope.all_keys.values()
    )
    remaining_model_keys: frozenset[CompiledObjectKey] = frozenset(
        key
        for key in stale_keys
        if key.resource_type == CompiledResourceType.MODEL and key.name not in reusable_model_names
    )
    remaining_model_changes: dict[str, ChangeDetectionResult] = detect_model_changes_in_scope(
        project=project,
        scope=replace(
            scopes.stale_warning_scope,
            selected_keys=remaining_model_keys,
        ),
        snapshot=snapshot,
        query_change_tracking=True,
        expected_version_hashes=identities.stale_warning_identities.model_version_hashes,
        expected_metadata_jsons=identities.stale_warning_identities.model_metadata_jsons,
    )
    return PlannerChangeResults(
        models={
            **{
                name: change
                for name, change in execution_changes.models.items()
                if name in reusable_model_names
            },
            **remaining_model_changes,
        },
        functions={},
    )


def _reusable_execution_model_names(
    *,
    identities: PlannerIdentityContext,
    execution_changes: PlannerChangeResults,
    query_change_tracking: bool,
) -> frozenset[str]:
    if not query_change_tracking:
        return frozenset()
    execution_identities: DirectModelVersionIdentities = identities.version_identities
    stale_identities: DirectModelVersionIdentities = identities.stale_warning_identities
    return frozenset(
        model_name
        for model_name in execution_changes.models
        if (
            execution_identities.model_version_hashes.get(model_name)
            == stale_identities.model_version_hashes.get(model_name)
            and execution_identities.model_metadata_jsons.get(model_name)
            == stale_identities.model_metadata_jsons.get(model_name)
        )
    )
