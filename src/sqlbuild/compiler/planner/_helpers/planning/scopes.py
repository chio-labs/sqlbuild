"""Scope resolution phase for execution planning."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.planner._helpers.graph.scope import build_planner_scope
from sqlbuild.compiler.planner.models import (
    PlannerPolicies,
    PlannerScope,
    PlannerScopeResolution,
    PlannerSelection,
)


def resolve_planner_scopes(
    *,
    project: CompiledProject,
    selection: PlannerSelection,
    policies: PlannerPolicies,
) -> PlannerScopeResolution:
    """Resolve selected, stale-warning, and inspection scopes for one plan."""

    selected_scope: PlannerScope = build_planner_scope(
        project=project,
        select=selection.select,
        exclude=selection.exclude,
        auto_load_sources=policies.auto_load_sources,
        selected_keys=selection.selected_keys,
    )
    stale_warning_scope: PlannerScope = replace(
        build_planner_scope(
            project=project,
            select=(),
            exclude=(),
            auto_load_sources=policies.auto_load_sources,
        ),
        selected_keys=selected_scope.selected_keys,
        user_selected_keys=selected_scope.user_selected_keys,
    )
    return PlannerScopeResolution(
        selected_scope=selected_scope,
        stale_warning_scope=stale_warning_scope,
        inspection_scope=selected_scope,
    )
