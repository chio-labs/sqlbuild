"""Top-level planner orchestration producing an execution plan."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationDestination,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.helpers.cascade import resolve_cascades
from sqlbuild.compiler.planner.helpers.changes.detect import detect_changes
from sqlbuild.compiler.planner.helpers.changes_only import (
    build_standard_identity_stale_model_names,
    mark_version_identity_stale_actions,
    prune_unchanged_scope,
)
from sqlbuild.compiler.planner.helpers.plan_entry import (
    build_plan_entries,
    build_planner_relations_context,
)
from sqlbuild.compiler.planner.helpers.plan_output import build_plan_output
from sqlbuild.compiler.planner.helpers.scope import build_planner_scope
from sqlbuild.compiler.planner.helpers.source_freshness import build_planner_source_freshness_result
from sqlbuild.compiler.planner.helpers.standard_reuse_decisions import (
    build_standard_reuse_decisions,
)
from sqlbuild.compiler.planner.helpers.standard_reuse_source import (
    build_standard_reuse_source_snapshot,
)
from sqlbuild.compiler.planner.helpers.version_identity import (
    StandardModelVersionIdentities,
    build_standard_model_version_identities,
)
from sqlbuild.compiler.planner.helpers.warehouse_snapshot import build_warehouse_snapshot
from sqlbuild.compiler.planner.models import (
    CursorOverrides,
    PlannerChangeResults,
    PlannerModelEntryResults,
    PlannerRelationsContext,
    PlannerResolvedActions,
    PlannerScope,
    PlanOutput,
    StandardReuseDecisionResults,
    StandardReuseSourceSnapshot,
    WarehouseSnapshot,
)
from sqlbuild.compiler.source_freshness.models import StandardSourceFreshnessPlanningResult
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig


def build_execution_plan(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    full_refresh: bool = False,
    changes_only: bool = False,
    start_cursor_override: str | None = None,
    end_cursor_override: str | None = None,
    cursor_overrides: CursorOverrides | None = None,
    auto_load_sources: bool = False,
    reload_sources: bool = False,
    on_progress: Callable[[str], None] | None = None,
    deferred_targets: dict[str, CompiledRelationDestination] | None = None,
    deferred_relations: dict[str, RelationInfo] | None = None,
    project_config: ProjectConfig | None = None,
    local_config: LocalConfig | None = None,
    defer_sources_to: str | None = None,
    source_deferral_enabled: bool = True,
    selected_keys: frozenset[CompiledObjectKey] | None = None,
) -> PlanOutput:
    scope: PlannerScope = build_planner_scope(
        project=project,
        select=select,
        exclude=exclude,
        auto_load_sources=auto_load_sources,
        selected_keys=selected_keys,
    )

    warehouse_start: float = time.monotonic()
    if on_progress is not None:
        on_progress("Inspecting warehouse state...")
    snapshot: WarehouseSnapshot = build_warehouse_snapshot(
        project=project,
        adapter=adapter,
        connection=connection,
        scope=scope,
        full_refresh=full_refresh,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        on_progress=on_progress,
        deferred_targets=deferred_targets,
        deferred_relations=deferred_relations,
    )
    relations: PlannerRelationsContext = build_planner_relations_context(
        project=project,
        adapter=adapter,
        connection=connection,
        scope=scope,
        deferred_targets=deferred_targets,
        project_config=project_config,
        local_config=local_config,
        defer_sources_to=defer_sources_to,
        source_deferral_enabled=source_deferral_enabled,
    )
    if on_progress is not None:
        on_progress(f"Inspected warehouse state. ({time.monotonic() - warehouse_start:.2f}s)")
        on_progress("Generating plan...")
    plan_start: float = time.monotonic()
    standard_reuse_source: StandardReuseSourceSnapshot | None = (
        None
        if full_refresh
        else build_standard_reuse_source_snapshot(
            project=project,
            adapter=adapter,
            connection=connection,
            scope=scope,
            project_config=project_config,
            local_config=local_config,
        )
    )
    version_identities: StandardModelVersionIdentities = build_standard_model_version_identities(
        functions=project.functions,
        scope=scope,
    )
    standard_reuse_decisions: StandardReuseDecisionResults | None = None
    if standard_reuse_source is not None:
        standard_reuse_decisions = build_standard_reuse_decisions(
            scope=scope,
            expected_version_hashes=version_identities.model_version_hashes,
            built_fingerprints=snapshot.fingerprints,
            source_snapshot=standard_reuse_source,
        )

    changes: PlannerChangeResults = detect_changes(
        project=project,
        scope=scope,
        snapshot=snapshot,
        full_refresh=full_refresh,
        expected_version_hashes=version_identities.model_version_hashes,
        expected_metadata_jsons=version_identities.model_metadata_jsons,
    )
    resolved_actions: PlannerResolvedActions = resolve_cascades(
        scope=scope,
        changes=changes,
    )
    source_freshness: StandardSourceFreshnessPlanningResult | None = None
    if changes_only:
        source_freshness = build_planner_source_freshness_result(
            project=project,
            adapter=adapter,
            connection=connection,
            scope=scope,
            relations=relations,
        )
    if changes_only and not full_refresh:
        standard_identity_stale_model_names: frozenset[str] = (
            build_standard_identity_stale_model_names(
                scope=scope,
                expected_version_hashes=version_identities.model_version_hashes,
                built_version_hashes={
                    model_name: fingerprint.version_hash
                    for model_name, fingerprint in snapshot.fingerprints.items()
                },
            )
        )
        scope = prune_unchanged_scope(
            scope=scope,
            changes=changes,
            resolved_actions=resolved_actions,
            source_freshness=source_freshness,
            expected_version_hashes=version_identities.model_version_hashes,
        )
        resolved_actions = mark_version_identity_stale_actions(
            scope=scope,
            resolved_actions=resolved_actions,
            expected_version_hashes=version_identities.model_version_hashes,
        )
    else:
        standard_identity_stale_model_names = frozenset()
    model_entry_results: PlannerModelEntryResults = build_plan_entries(
        project=project,
        adapter=adapter,
        scope=scope,
        snapshot=snapshot,
        relations=relations,
        resolved_actions=resolved_actions,
        cursor_overrides=cursor_overrides,
        full_refresh=full_refresh,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
    )
    plan_output: PlanOutput = build_plan_output(
        project=project,
        adapter=adapter,
        scope=scope,
        snapshot=snapshot,
        relations=relations,
        changes=changes,
        model_entry_results=model_entry_results,
        reload_sources=reload_sources,
    )
    if source_freshness is not None:
        standard_remaining_stale_model_names: tuple[str, ...] = tuple(
            sorted(
                standard_identity_stale_model_names
                - frozenset(
                    key.name
                    for key in scope.selected_keys
                    if key.resource_type == CompiledResourceType.MODEL
                )
            )
        )
        plan_output = replace(
            plan_output,
            source_freshness=source_freshness,
            metadata={
                **plan_output.metadata,
                "standard_source_freshness": _serialize_standard_source_freshness_metadata(
                    source_freshness
                ),
                "standard_remaining_stale_model_names": standard_remaining_stale_model_names,
            },
        )
    if standard_reuse_source is not None:
        plan_output = replace(
            plan_output,
            metadata={
                **plan_output.metadata,
                **_serialize_standard_reuse_metadata(
                    standard_reuse_source=standard_reuse_source,
                    standard_reuse_decisions=standard_reuse_decisions,
                ),
            },
        )
    if on_progress is not None:
        on_progress(f"Generated plan. ({time.monotonic() - plan_start:.2f}s)")
    return plan_output


def _serialize_standard_source_freshness_metadata(
    source_freshness: StandardSourceFreshnessPlanningResult,
) -> dict[str, object]:
    changed_source_names: tuple[str, ...] = tuple(
        sorted(identity.source_name for identity in source_freshness.changed_identities)
    )
    unchanged_source_names: tuple[str, ...] = tuple(
        sorted(identity.source_name for identity in source_freshness.unchanged_identities)
    )
    stale_model_names: tuple[str, ...] = (
        tuple(sorted(source_freshness.propagation.stale_model_names))
        if source_freshness.propagation is not None
        else ()
    )
    return {
        "observed_source_names": tuple(
            sorted(record.source_name for record in source_freshness.observed_records)
        ),
        "changed_source_names": changed_source_names,
        "unchanged_source_names": unchanged_source_names,
        "unknown_source_names": tuple(sorted(source_freshness.unknown_source_names)),
        "stale_model_names": stale_model_names,
    }


def _serialize_standard_reuse_metadata(
    *,
    standard_reuse_source: StandardReuseSourceSnapshot,
    standard_reuse_decisions: StandardReuseDecisionResults | None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "standard_reuse_source": {
            "target_name": standard_reuse_source.target_name,
            "fingerprint_database": standard_reuse_source.fingerprint_database,
            "fingerprint_schema": standard_reuse_source.fingerprint_schema,
            "models": {
                model_name: {
                    "database": model_snapshot.destination.database,
                    "schema": model_snapshot.destination.schema,
                    "name": model_snapshot.destination.name,
                    "qualified_name": model_snapshot.destination.qualified_name,
                    "relation_exists": model_snapshot.relation_exists,
                    "built_version_present": model_snapshot.built_version_hash is not None,
                }
                for model_name, model_snapshot in sorted(
                    standard_reuse_source.model_snapshots.items()
                )
            },
        }
    }
    if standard_reuse_decisions is None:
        return metadata
    metadata["standard_reuse_decisions"] = {
        "target_name": standard_reuse_source.target_name,
        "source_target_name": standard_reuse_decisions.source_target_name,
        "models": {
            model_name: {
                "decision": decision.decision,
                "source_target_name": decision.source_target_name,
                "source_relation_exists": decision.source_relation_exists,
                "source_built_version_present": decision.source_built_version_present,
                "source_matches_expected": decision.source_matches_expected,
            }
            for model_name, decision in sorted(standard_reuse_decisions.models.items())
        },
    }
    return metadata
