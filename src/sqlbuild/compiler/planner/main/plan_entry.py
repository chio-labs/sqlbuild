"""Public model plan-entry phase entrypoint."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledProject, CompiledRelationLocation
from sqlbuild.compiler.planner.helpers.cascade import resolve_cascades
from sqlbuild.compiler.planner.helpers.changes.detect import detect_changes
from sqlbuild.compiler.planner.helpers.plan_entry import (
    build_plan_entries,
    build_planner_relations_context,
)
from sqlbuild.compiler.planner.helpers.plan_output import build_plan_output
from sqlbuild.compiler.planner.models import (
    ChangeDetectionResult,
    CursorOverrides,
    PlannerChangeResults,
    PlannerModelEntryResults,
    PlannerRelationsContext,
    PlannerResolvedActions,
    PlannerScope,
    PlanOutput,
    WarehouseSnapshot,
)
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig


def build_plan_output_from_model_changes_phase(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    scope: PlannerScope,
    snapshot: WarehouseSnapshot,
    model_changes: dict[str, ChangeDetectionResult],
    cursor_overrides: CursorOverrides | None = None,
    full_refresh: bool = False,
    start_cursor_override: str | None = None,
    end_cursor_override: str | None = None,
    reload_sources: bool = False,
    deferred_targets: dict[str, CompiledRelationLocation] | None = None,
    project_config: ProjectConfig | None = None,
    local_config: LocalConfig | None = None,
    defer_sources_to: str | None = None,
    source_deferral_enabled: bool = True,
) -> PlanOutput:
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
    detected_changes: PlannerChangeResults = detect_changes(
        project=project,
        scope=scope,
        snapshot=snapshot,
        full_refresh=full_refresh,
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
        cursor_overrides=cursor_overrides,
        full_refresh=full_refresh,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
    )
    return build_plan_output(
        project=project,
        adapter=adapter,
        scope=scope,
        snapshot=snapshot,
        relations=relations,
        changes=changes,
        model_entry_results=model_entry_results,
        reload_sources=reload_sources,
    )
