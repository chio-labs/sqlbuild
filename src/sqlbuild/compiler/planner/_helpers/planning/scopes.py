"""Scope resolution phase for execution planning."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
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
    full_scope: PlannerScope = build_planner_scope(
        project=project,
        select=(),
        exclude=(),
        auto_load_sources=policies.auto_load_sources,
    )
    stale_warning_keys: frozenset[CompiledObjectKey] = _upstream_closure(
        selected_keys=selected_scope.selected_keys,
        upstream_deps=full_scope.upstream_deps,
    )
    stale_warning_scope: PlannerScope = replace(
        full_scope,
        all_keys={
            name: key for name, key in full_scope.all_keys.items() if key in stale_warning_keys
        },
        models_by_name={
            name: model
            for name, model in full_scope.models_by_name.items()
            if model.key in stale_warning_keys
        },
        selected_keys=selected_scope.selected_keys,
        execution_order=tuple(
            key for key in full_scope.execution_order if key in stale_warning_keys
        ),
        user_selected_keys=selected_scope.user_selected_keys,
    )
    return PlannerScopeResolution(
        selected_scope=selected_scope,
        stale_warning_scope=stale_warning_scope,
        inspection_scope=selected_scope,
    )


def _upstream_closure(
    *,
    selected_keys: frozenset[CompiledObjectKey],
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[CompiledObjectKey]:
    closure: set[CompiledObjectKey] = set(selected_keys)
    pending: list[CompiledObjectKey] = list(selected_keys)
    while pending:
        key: CompiledObjectKey = pending.pop()
        upstream_key: CompiledObjectKey
        for upstream_key in upstream_deps.get(key, ()):
            if upstream_key in closure:
                continue
            closure.add(upstream_key)
            pending.append(upstream_key)
    return frozenset(closure)
