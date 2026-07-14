"""Version identity and stale-warning change phases for execution planning."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.planner._helpers.changes.detect import detect_changes
from sqlbuild.compiler.planner._helpers.identity.standard import (
    build_standard_model_version_identities,
)
from sqlbuild.compiler.planner.models import (
    PlannerChangeResults,
    PlannerIdentityContext,
    PlannerScopeResolution,
    WarehouseSnapshot,
)


def build_planner_identity_context(
    *,
    project: CompiledProject,
    scopes: PlannerScopeResolution,
) -> PlannerIdentityContext:
    """Build expected version identities for the inspection and stale-warning scopes."""

    return PlannerIdentityContext(
        version_identities=build_standard_model_version_identities(
            functions=project.functions,
            seeds=project.seeds,
            scope=scopes.inspection_scope,
        ),
        stale_warning_identities=build_standard_model_version_identities(
            functions=project.functions,
            seeds=project.seeds,
            scope=scopes.stale_warning_scope,
        ),
    )


def detect_stale_warning_changes(
    *,
    project: CompiledProject,
    scopes: PlannerScopeResolution,
    snapshot: WarehouseSnapshot,
    identities: PlannerIdentityContext,
) -> PlannerChangeResults:
    """Detect project-wide changes used for stale-out-of-selection warnings."""

    return detect_changes(
        project=project,
        scope=replace(
            scopes.stale_warning_scope,
            selected_keys=frozenset(scopes.stale_warning_scope.all_keys.values()),
        ),
        snapshot=snapshot,
        full_refresh=False,
        expected_version_hashes=identities.stale_warning_identities.model_version_hashes,
        expected_metadata_jsons=identities.stale_warning_identities.model_metadata_jsons,
    )
