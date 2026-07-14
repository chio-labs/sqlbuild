"""Public model plan-entry phase entrypoint."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.planner._helpers.changes.detect import detect_changes
from sqlbuild.compiler.planner._helpers.output.plan_entry import (
    build_plan_entries,
    build_planner_relations_context,
)
from sqlbuild.compiler.planner._helpers.output.plan_output import build_plan_output
from sqlbuild.compiler.planner._helpers.pruning.cascade import resolve_cascades
from sqlbuild.compiler.planner.models import (
    ChangeDetectionResult,
    DeferralInputs,
    ModelChangesPlanInputs,
    PlannerChangeResults,
    PlannerModelEntryResults,
    PlannerRelationsContext,
    PlannerResolvedActions,
    PlannerScope,
    PlanOutput,
    PlanOutputExtras,
    WarehouseSnapshot,
)


def build_plan_output_from_model_changes_phase(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    scope: PlannerScope,
    snapshot: WarehouseSnapshot,
    model_changes: dict[str, ChangeDetectionResult],
    inputs: ModelChangesPlanInputs | None = None,
) -> PlanOutput:
    resolved: ModelChangesPlanInputs = inputs if inputs is not None else ModelChangesPlanInputs()
    relations: PlannerRelationsContext = build_planner_relations_context(
        project=project,
        adapter=adapter,
        connection=connection,
        scope=scope,
        deferral=DeferralInputs(
            deferred_locations=resolved.deferred_locations,
            defer_sources_to=resolved.defer_sources_to,
            source_deferral_enabled=resolved.source_deferral_enabled,
        ),
        project_config=resolved.project_config,
        local_config=resolved.local_config,
    )
    detected_changes: PlannerChangeResults = detect_changes(
        project=project,
        scope=scope,
        snapshot=snapshot,
        full_refresh=resolved.full_refresh,
    )
    changes: PlannerChangeResults = replace(detected_changes, models=model_changes)
    resolved_actions: PlannerResolvedActions = resolve_cascades(
        scope=scope,
        changes=changes,
    )
    model_entry_results: PlannerModelEntryResults = build_plan_entries(
        project=project,
        adapter=adapter,
        scope=scope,
        snapshot=snapshot,
        relations=relations,
        resolved_actions=resolved_actions,
        cursor_overrides=resolved.cursor_overrides,
        full_refresh=resolved.full_refresh,
    )
    return build_plan_output(
        project=project,
        adapter=adapter,
        scope=scope,
        snapshot=snapshot,
        relations=relations,
        changes=changes,
        model_entry_results=model_entry_results,
        reload_sources=resolved.reload_sources,
        extras=PlanOutputExtras(
            seed_version_hashes=resolved.seed_version_hashes,
            seed_metadata_jsons=resolved.seed_metadata_jsons,
            seed_plan_reasons=resolved.seed_plan_reasons,
        ),
    )
