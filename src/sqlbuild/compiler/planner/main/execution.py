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
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.helpers.changes.detect import detect_changes
from sqlbuild.compiler.planner.helpers.graph.buildability import check_buildability
from sqlbuild.compiler.planner.helpers.graph.scope import build_planner_scope
from sqlbuild.compiler.planner.helpers.identity.honest import (
    with_honest_model_write_hashes,
)
from sqlbuild.compiler.planner.helpers.identity.standard import (
    StandardModelVersionIdentities,
    build_standard_model_version_identities,
)
from sqlbuild.compiler.planner.helpers.output.plan_entry import (
    build_plan_entries,
    build_planner_relations_context,
)
from sqlbuild.compiler.planner.helpers.output.plan_output import build_plan_output
from sqlbuild.compiler.planner.helpers.pruning.cascade import resolve_cascades
from sqlbuild.compiler.planner.helpers.pruning.selection_staleness import (
    build_stale_out_of_selection_warnings,
)
from sqlbuild.compiler.planner.helpers.pruning.standard_scope import (
    build_standard_identity_stale_model_names,
    mark_direct_parent_run_actions,
    mark_run_despite_unchanged_actions,
    mark_version_identity_stale_actions,
    prune_standard_unchanged_scope,
)
from sqlbuild.compiler.planner.helpers.reuse.dependency_baseline import (
    build_dependency_baseline_candidate_keys,
    build_dependency_baseline_entries,
    build_existing_destination_input_entries,
    with_dependency_baseline_candidates,
)
from sqlbuild.compiler.planner.helpers.reuse.standard_reuse_decisions import (
    is_standard_reuse_decision_reusable,
)
from sqlbuild.compiler.planner.helpers.reuse.standard_reuse_from_target import (
    enforce_standard_reuse_from_source_deferral_conflict,
)
from sqlbuild.compiler.planner.helpers.reuse.standard_reuse_planning import (
    build_standard_reuse_planning_result,
    serialize_standard_reuse_metadata,
    serialize_standard_reuse_plan_metadata,
)
from sqlbuild.compiler.planner.helpers.warehouse.snapshot import gather_warehouse_snapshot
from sqlbuild.compiler.planner.helpers.warehouse.source_freshness import (
    build_planner_source_freshness_result,
)
from sqlbuild.compiler.planner.main.run_despite_unchanged import (
    build_run_despite_unchanged_planning_result,
)
from sqlbuild.compiler.planner.models import (
    ChangeDetectionResult,
    CursorOverrides,
    DependencyBaselinePlanEntry,
    ExistingDestinationInputPlanEntry,
    MissingUpstream,
    PlannerChangeResults,
    PlannerModelEntryResults,
    PlannerRelationsContext,
    PlannerResolvedActions,
    PlannerScope,
    PlanOutput,
    PlanWarning,
    ResolvedModelAction,
    RunDespiteUnchangedPlanningResult,
    StandardReusePlanningResult,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import (
    ChangeKind,
    StandardScopePruning,
)
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
    enable_reuse_planning: bool = True,
) -> PlanOutput:
    selected_scope: PlannerScope = build_planner_scope(
        project=project,
        select=select,
        exclude=exclude,
        auto_load_sources=auto_load_sources,
        selected_keys=selected_keys,
    )
    project_scope_for_stale_warnings: PlannerScope = replace(
        build_planner_scope(
            project=project,
            select=(),
            exclude=(),
            auto_load_sources=auto_load_sources,
        ),
        selected_keys=selected_scope.selected_keys,
    )
    dependency_baseline_candidate_keys: frozenset[CompiledObjectKey] = (
        build_dependency_baseline_candidate_keys(selected_scope)
        if enable_reuse_planning
        else frozenset()
    )
    scope: PlannerScope = with_dependency_baseline_candidates(
        scope=selected_scope,
        candidate_keys=dependency_baseline_candidate_keys,
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
    snapshot: WarehouseSnapshot = gather_warehouse_snapshot(
        project=project,
        adapter=adapter,
        connection=connection,
        execute=adapter.execute,
        selected_keys=frozenset(project_scope_for_stale_warnings.all_keys.values()),
        full_refresh=full_refresh,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        on_progress=on_progress,
        deferred_locations=deferred_locations,
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
        require_source_deferral_config=False,
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
    stale_warning_version_identities: StandardModelVersionIdentities = (
        build_standard_model_version_identities(
            functions=project.functions,
            seeds=project.seeds,
            scope=project_scope_for_stale_warnings,
        )
    )
    stale_warning_changes: PlannerChangeResults = detect_changes(
        project=project,
        scope=replace(
            project_scope_for_stale_warnings,
            selected_keys=frozenset(project_scope_for_stale_warnings.all_keys.values()),
        ),
        snapshot=snapshot,
        full_refresh=False,
        expected_version_hashes=stale_warning_version_identities.model_version_hashes,
        expected_metadata_jsons=stale_warning_version_identities.model_metadata_jsons,
    )
    standard_reuse: StandardReusePlanningResult | None = (
        build_standard_reuse_planning_result(
            project=project,
            adapter=adapter,
            connection=connection,
            scope=scope,
            relations=relations,
            project_config=project_config,
            local_config=local_config,
            expected_version_hashes=version_identities.model_version_hashes,
            built_fingerprints=snapshot.fingerprints.models,
            destination_relation_names=frozenset(snapshot.existing_relations),
            cursor_snapshots=snapshot.cursor_snapshots,
            full_refresh=full_refresh,
            custom_prepare_version_materializations=custom_prepare_version_materializations,
        )
        if enable_reuse_planning
        else None
    )
    reusable_dependency_baseline_keys: frozenset[CompiledObjectKey] = frozenset(
        key
        for key in dependency_baseline_candidate_keys
        if standard_reuse is not None
        and standard_reuse.decisions.models.get(key.name) is not None
        and is_standard_reuse_decision_reusable(standard_reuse.decisions.models[key.name].decision)
    )
    external_seed_keys: frozenset[CompiledObjectKey] = frozenset(
        seed.key for seed in project.seeds if seed.external
    )
    missing: tuple[MissingUpstream, ...] = check_buildability(
        selected_keys=selected_scope.selected_keys,
        upstream_deps=selected_scope.upstream_deps,
        snapshot=snapshot,
        deferred_relations=deferred_relations,
        satisfied_keys=reusable_dependency_baseline_keys | external_seed_keys,
    )
    if missing:
        names: str = ", ".join(m.key.name for m in missing[:5])
        raise PlannerInputError(
            f"cannot build selected scope: {len(missing)} missing upstream dependencies ({names})",
            code="S301",
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
            freshness_state_schemas=snapshot.source_freshness_state_schemas,
        )
    )
    original_scope_for_stale_warnings: PlannerScope = project_scope_for_stale_warnings
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
            changes=stale_warning_changes,
            resolved_actions=resolved_actions,
            source_freshness=source_freshness,
            run_despite_unchanged=run_despite_unchanged,
            forced_stale_model_names=forced_stale_model_names,
            expected_version_hashes=version_identities.model_version_hashes,
            expected_seed_version_hashes=version_identities.seed_version_hashes,
            built_seed_fingerprints=snapshot.fingerprints.seeds,
            user_selected_keys=selected_scope.selected_keys,
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
        resolved_actions = mark_direct_parent_run_actions(
            scope=scope,
            resolved_actions=resolved_actions,
        )
    else:
        standard_identity_stale_model_names = frozenset()
        run_despite_unchanged = RunDespiteUnchangedPlanningResult()
    execution_scope: PlannerScope = replace(
        scope,
        selected_keys=scope.selected_keys - dependency_baseline_candidate_keys,
    )
    baseline_model_hashes: dict[str, str] = {}
    if standard_reuse is not None:
        key: CompiledObjectKey
        for key in reusable_dependency_baseline_keys:
            baseline_hash: str | None = standard_reuse.snapshot.model_snapshots[
                key.name
            ].built_version_hash
            if baseline_hash is not None:
                baseline_model_hashes[key.name] = baseline_hash
    changes = with_honest_model_write_hashes(
        scope=execution_scope,
        snapshot=snapshot,
        changes=changes,
        version_identities=version_identities,
        available_model_hashes=baseline_model_hashes,
    )
    recomputed_resolved_models: dict[str, ResolvedModelAction] = {}
    for model_name, resolved in resolved_actions.models.items():
        recomputed_change: ChangeDetectionResult | None = changes.models.get(model_name)
        if recomputed_change is None:
            recomputed_change = resolved.change
        elif (
            resolved.change.change_kind == ChangeKind.RUN_DESPITE_UNCHANGED
            and recomputed_change.change_kind == ChangeKind.NO_CHANGE
        ):
            recomputed_change = replace(
                recomputed_change,
                change_kind=ChangeKind.RUN_DESPITE_UNCHANGED,
                backfill=resolved.change.backfill,
            )
        recomputed_resolved_models[model_name] = replace(resolved, change=recomputed_change)
    resolved_actions = replace(resolved_actions, models=recomputed_resolved_models)
    dependency_baseline_scope: PlannerScope = replace(
        scope,
        selected_keys=reusable_dependency_baseline_keys,
    )
    execution_relations: PlannerRelationsContext = build_planner_relations_context(
        project=project,
        adapter=adapter,
        connection=connection,
        scope=execution_scope,
        deferred_locations=deferred_locations,
        project_config=project_config,
        local_config=local_config,
        defer_sources_to=defer_sources_to,
        source_deferral_enabled=source_deferral_enabled,
    )
    dependency_baseline_relations: PlannerRelationsContext = build_planner_relations_context(
        project=project,
        adapter=adapter,
        connection=connection,
        scope=dependency_baseline_scope,
        deferred_locations=deferred_locations,
        project_config=project_config,
        local_config=local_config,
        defer_sources_to=defer_sources_to,
        source_deferral_enabled=source_deferral_enabled,
    )
    dependency_baseline_entry_results: PlannerModelEntryResults = build_plan_entries(
        project=project,
        adapter=adapter,
        scope=dependency_baseline_scope,
        snapshot=snapshot,
        relations=dependency_baseline_relations,
        resolved_actions=resolved_actions,
        cursor_overrides=cursor_overrides,
        full_refresh=full_refresh,
        standard_reuse_decisions=(standard_reuse.decisions if standard_reuse is not None else None),
        run_despite_unchanged=RunDespiteUnchangedPlanningResult(),
        source_freshness_blocked_model_names=frozenset(),
        external_blocked_model_names=frozenset(),
        custom_prepare_version_materializations=custom_prepare_version_materializations,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
    )
    dependency_baseline_entries: tuple[DependencyBaselinePlanEntry, ...] = (
        build_dependency_baseline_entries(
            entries=dependency_baseline_entry_results.entries,
            candidate_keys=reusable_dependency_baseline_keys,
        )
    )
    existing_destination_input_entries: tuple[ExistingDestinationInputPlanEntry, ...] = (
        build_existing_destination_input_entries(
            scope=scope,
            candidate_keys=dependency_baseline_candidate_keys,
            reusable_keys=reusable_dependency_baseline_keys,
            existing_relation_names=frozenset(snapshot.existing_relations),
            expected_version_hashes=version_identities.model_version_hashes,
            destination_fingerprints=snapshot.fingerprints.models,
        )
        if enable_reuse_planning
        else ()
    )
    model_entry_results: PlannerModelEntryResults = build_plan_entries(
        project=project,
        adapter=adapter,
        scope=execution_scope,
        snapshot=snapshot,
        relations=execution_relations,
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
        scope=execution_scope,
        snapshot=snapshot,
        relations=relations,
        changes=changes,
        model_entry_results=model_entry_results,
        dependency_baseline_entries=dependency_baseline_entries,
        existing_destination_input_entries=existing_destination_input_entries,
        reload_sources=reload_sources,
        seed_version_hashes=version_identities.seed_version_hashes,
        seed_metadata_jsons=version_identities.seed_metadata_jsons,
    )
    reuse_satisfied_model_names: frozenset[str] = (
        frozenset(
            name
            for name, decision in standard_reuse.decisions.models.items()
            if is_standard_reuse_decision_reusable(decision.decision)
        )
        if standard_reuse is not None
        else frozenset()
    )
    stale_out_of_selection_warnings: tuple[PlanWarning, ...] = (
        build_stale_out_of_selection_warnings(
            original_scope=original_scope_for_stale_warnings,
            execution_scope=execution_scope,
            changes=stale_warning_changes,
            snapshot=snapshot,
            version_identities=stale_warning_version_identities,
            source_freshness=source_freshness,
            reuse_satisfied_model_names=reuse_satisfied_model_names,
        )
    )
    if stale_out_of_selection_warnings:
        plan_output = replace(
            plan_output,
            warnings=(*plan_output.warnings, *stale_out_of_selection_warnings),
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
                **serialize_standard_reuse_plan_metadata(
                    model_entries=plan_output.model_entries,
                    dependency_baseline_entries=plan_output.dependency_baseline_entries,
                    existing_destination_input_entries=(
                        plan_output.existing_destination_input_entries
                    ),
                ),
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
