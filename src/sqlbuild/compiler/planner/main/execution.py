"""Top-level planner orchestration producing an execution plan."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.helpers.cascade import resolve_cascades
from sqlbuild.compiler.planner.helpers.changes.detect import detect_changes
from sqlbuild.compiler.planner.helpers.plan_entry import (
    build_plan_entries,
    build_planner_relations_context,
)
from sqlbuild.compiler.planner.helpers.plan_output import build_plan_output
from sqlbuild.compiler.planner.helpers.scope import build_planner_scope
from sqlbuild.compiler.planner.helpers.source_freshness import (
    build_planner_source_freshness_result,
)
from sqlbuild.compiler.planner.helpers.standard_reuse_from_target import (
    enforce_standard_reuse_from_source_deferral_conflict,
)
from sqlbuild.compiler.planner.helpers.standard_reuse_planning import (
    build_standard_reuse_planning_result,
    serialize_standard_reuse_metadata,
)
from sqlbuild.compiler.planner.helpers.standard_scope_pruning import (
    build_standard_identity_stale_model_names,
    mark_run_despite_unchanged_actions,
    mark_version_identity_stale_actions,
    prune_standard_unchanged_scope,
)
from sqlbuild.compiler.planner.helpers.version_identity import (
    StandardModelVersionIdentities,
    build_standard_model_version_identities,
)
from sqlbuild.compiler.planner.helpers.warehouse_snapshot import build_warehouse_snapshot
from sqlbuild.compiler.planner.main.run_despite_unchanged import (
    build_run_despite_unchanged_planning_result,
)
from sqlbuild.compiler.planner.models import (
    CursorOverrides,
    PlannerChangeResults,
    PlannerModelEntryResults,
    PlannerRelationsContext,
    PlannerResolvedActions,
    PlannerScope,
    PlanOutput,
    RunDespiteUnchangedPlanningResult,
    StandardReusePlanningResult,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import StandardScopePruning
from sqlbuild.compiler.source_freshness.models import StandardSourceFreshnessPlanningResult
from sqlbuild.compiler.source_freshness.types import SourceFreshnessAgeStatus
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig


def build_execution_plan(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    full_refresh: bool = False,
    standard_scope_pruning: StandardScopePruning = StandardScopePruning.NONE,
    start_cursor_override: str | None = None,
    end_cursor_override: str | None = None,
    cursor_overrides: CursorOverrides | None = None,
    auto_load_sources: bool = False,
    reload_sources: bool = False,
    forced_stale_model_names: tuple[str, ...] = (),
    external_blocked_model_names: tuple[str, ...] = (),
    on_progress: Callable[[str], None] | None = None,
    deferred_locations: dict[str, CompiledRelationLocation] | None = None,
    deferred_relations: dict[str, RelationInfo] | None = None,
    project_config: ProjectConfig | None = None,
    local_config: LocalConfig | None = None,
    defer_sources_to: str | None = None,
    source_deferral_enabled: bool = True,
    selected_keys: frozenset[CompiledObjectKey] | None = None,
    custom_prepare_version_materializations: frozenset[str] = frozenset(),
) -> PlanOutput:
    scope: PlannerScope = build_planner_scope(
        project=project,
        select=select,
        exclude=exclude,
        auto_load_sources=auto_load_sources,
        selected_keys=selected_keys,
    )
    enforce_standard_reuse_from_source_deferral_conflict(
        project=project,
        project_config=project_config,
        local_config=local_config,
        defer_sources_to=defer_sources_to,
        source_deferral_enabled=source_deferral_enabled,
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
        deferred_locations=deferred_locations,
        deferred_relations=deferred_relations,
    )
    relations: PlannerRelationsContext = build_planner_relations_context(
        project=project,
        adapter=adapter,
        connection=connection,
        scope=scope,
        deferred_locations=deferred_locations,
        project_config=project_config,
        local_config=local_config,
        defer_sources_to=defer_sources_to,
        source_deferral_enabled=source_deferral_enabled,
    )
    if on_progress is not None:
        on_progress(f"Inspected warehouse state. ({time.monotonic() - warehouse_start:.2f}s)")
        on_progress("Generating plan...")
    plan_start: float = time.monotonic()
    version_identities: StandardModelVersionIdentities = build_standard_model_version_identities(
        functions=project.functions,
        seeds=project.seeds,
        scope=scope,
    )
    standard_reuse: StandardReusePlanningResult | None = build_standard_reuse_planning_result(
        project=project,
        adapter=adapter,
        connection=connection,
        scope=scope,
        relations=relations,
        project_config=project_config,
        local_config=local_config,
        expected_version_hashes=version_identities.model_version_hashes,
        built_fingerprints=snapshot.fingerprints.models,
        cursor_snapshots=snapshot.cursor_snapshots,
        full_refresh=full_refresh,
        custom_prepare_version_materializations=custom_prepare_version_materializations,
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
    source_freshness: StandardSourceFreshnessPlanningResult | None = (
        build_planner_source_freshness_result(
            project=project,
            adapter=adapter,
            connection=connection,
            scope=scope,
            relations=relations,
        )
    )
    pruned_standard_model_names: tuple[str, ...] = ()
    if standard_scope_pruning == StandardScopePruning.PRUNE_UNCHANGED and not full_refresh:
        original_selected_model_names: frozenset[str] = frozenset(
            key.name
            for key in scope.selected_keys
            if key.resource_type == CompiledResourceType.MODEL
        )
        standard_identity_stale_model_names: frozenset[str] = (
            build_standard_identity_stale_model_names(
                scope=scope,
                expected_version_hashes=version_identities.model_version_hashes,
                built_version_hashes={
                    model_name: fingerprint.version_hash
                    for model_name, fingerprint in snapshot.fingerprints.models.items()
                },
                forced_stale_model_names=forced_stale_model_names,
            )
        )
        source_stale_model_names: frozenset[str] = (
            source_freshness.propagation.stale_model_names
            if source_freshness.propagation is not None
            else frozenset()
        )
        run_despite_unchanged: RunDespiteUnchangedPlanningResult = (
            build_run_despite_unchanged_planning_result(
                scope=scope,
                source_freshness=source_freshness,
                already_stale_model_names=(
                    standard_identity_stale_model_names | source_stale_model_names
                ),
                now=(
                    source_freshness.observed_records[0].observed_at
                    if source_freshness.observed_records
                    else datetime.now(UTC)
                ),
            )
        )
        scope = prune_standard_unchanged_scope(
            scope=scope,
            changes=changes,
            resolved_actions=resolved_actions,
            source_freshness=source_freshness,
            run_despite_unchanged=run_despite_unchanged,
            forced_stale_model_names=forced_stale_model_names,
            expected_version_hashes=version_identities.model_version_hashes,
            expected_seed_version_hashes=version_identities.seed_version_hashes,
            built_seed_fingerprints=snapshot.fingerprints.seeds,
        )
        pruned_standard_model_names = tuple(
            sorted(
                original_selected_model_names
                - frozenset(
                    key.name
                    for key in scope.selected_keys
                    if key.resource_type == CompiledResourceType.MODEL
                )
            )
        )
        resolved_actions = mark_version_identity_stale_actions(
            scope=scope,
            resolved_actions=resolved_actions,
            expected_version_hashes=version_identities.model_version_hashes,
            forced_stale_model_names=forced_stale_model_names,
        )
        resolved_actions = mark_run_despite_unchanged_actions(
            scope=scope,
            resolved_actions=resolved_actions,
            run_despite_unchanged=run_despite_unchanged,
        )
    else:
        standard_identity_stale_model_names = frozenset()
        run_despite_unchanged = RunDespiteUnchangedPlanningResult()
    model_entry_results: PlannerModelEntryResults = build_plan_entries(
        project=project,
        adapter=adapter,
        scope=scope,
        snapshot=snapshot,
        relations=relations,
        resolved_actions=resolved_actions,
        cursor_overrides=cursor_overrides,
        full_refresh=full_refresh,
        standard_reuse_decisions=(standard_reuse.decisions if standard_reuse is not None else None),
        run_despite_unchanged=run_despite_unchanged,
        source_freshness_blocked_model_names=(
            source_freshness.propagation.blocked_model_names
            if source_freshness is not None and source_freshness.propagation is not None
            else frozenset()
        ),
        external_blocked_model_names=frozenset(external_blocked_model_names),
        custom_prepare_version_materializations=custom_prepare_version_materializations,
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
        seed_version_hashes=version_identities.seed_version_hashes,
        seed_metadata_jsons=version_identities.seed_metadata_jsons,
    )
    if pruned_standard_model_names:
        plan_output = replace(
            plan_output,
            metadata={
                **plan_output.metadata,
                "standard_pruned_model_names": pruned_standard_model_names,
            },
        )
    if source_freshness is not None:
        standard_remaining_stale_model_names: tuple[str, ...] = tuple(
            sorted(
                (standard_identity_stale_model_names | run_despite_unchanged.stale_model_names)
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
                "standard_run_despite_unchanged": _serialize_run_despite_unchanged_metadata(
                    run_despite_unchanged
                ),
            },
        )
    if standard_reuse is not None:
        plan_output = replace(
            plan_output,
            metadata={
                **plan_output.metadata,
                **serialize_standard_reuse_metadata(standard_reuse),
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
    blocked_model_names: tuple[str, ...] = (
        tuple(sorted(source_freshness.propagation.blocked_model_names))
        if source_freshness.propagation is not None
        else ()
    )
    age_warning_source_names: tuple[str, ...] = tuple(
        sorted(
            identity.source_name
            for identity, status in source_freshness.age_statuses.items()
            if status == SourceFreshnessAgeStatus.WARN
        )
    )
    age_error_source_names: tuple[str, ...] = tuple(
        sorted(
            identity.source_name
            for identity, status in source_freshness.age_statuses.items()
            if status == SourceFreshnessAgeStatus.ERROR
        )
    )
    return {
        "observed_source_names": tuple(
            sorted(record.source_name for record in source_freshness.observed_records)
        ),
        "changed_source_names": changed_source_names,
        "unchanged_source_names": unchanged_source_names,
        "unknown_source_names": tuple(sorted(source_freshness.unknown_source_names)),
        "age_warning_source_names": age_warning_source_names,
        "age_error_source_names": age_error_source_names,
        "stale_model_names": stale_model_names,
        "blocked_model_names": blocked_model_names,
    }


def _serialize_run_despite_unchanged_metadata(
    run_despite_unchanged: RunDespiteUnchangedPlanningResult,
) -> dict[str, object]:
    return {
        "root_model_names": tuple(sorted(run_despite_unchanged.root_model_names)),
        "stale_model_names": tuple(sorted(run_despite_unchanged.stale_model_names)),
        "decisions": {
            model_name: {
                "mode": decision.mode.value,
                "duration": decision.duration,
                "newest_source_name": decision.newest_source_name,
                "newest_source_data_age_seconds": (decision.newest_source_data_age_seconds),
            }
            for model_name, decision in sorted(run_despite_unchanged.decisions.items())
        },
    }
