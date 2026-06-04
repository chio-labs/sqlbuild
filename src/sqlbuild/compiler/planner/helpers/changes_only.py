"""Direct changes-only planner scope pruning helpers."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    FunctionChangeResult,
    PlannerChangeResults,
    PlannerResolvedActions,
    PlannerScope,
    ResolvedModelAction,
)
from sqlbuild.compiler.planner.types import BackfillAction, ChangeKind, PlanReason


def prune_unchanged_scope(
    *,
    scope: PlannerScope,
    changes: PlannerChangeResults,
    resolved_actions: PlannerResolvedActions,
) -> PlannerScope:
    """Remove unchanged selected SQL nodes for direct changes-only planning."""

    selected_keys: set[CompiledObjectKey] = set()
    key: CompiledObjectKey
    for key in scope.selected_keys:
        if key.resource_type == CompiledResourceType.MODEL:
            resolved_action: ResolvedModelAction | None = resolved_actions.models.get(key.name)
            if resolved_action is not None and _model_action_is_stale(resolved_action):
                selected_keys.add(key)
            continue
        if key.resource_type == CompiledResourceType.FUNCTION:
            function_change: FunctionChangeResult | None = changes.functions.get(key.name)
            if function_change is not None and _function_action_is_stale(function_change):
                selected_keys.add(key)
            continue
        selected_keys.add(key)
    return replace(scope, selected_keys=frozenset(selected_keys))


def _model_action_is_stale(resolved_action: ResolvedModelAction) -> bool:
    change_kind: ChangeKind = resolved_action.change.change_kind
    if change_kind != ChangeKind.NO_CHANGE:
        return True
    if resolved_action.cascade is not None:
        return True
    return _backfill_is_stale(resolved_action.backfill)


def _function_action_is_stale(function_change: FunctionChangeResult) -> bool:
    if function_change.reason != PlanReason.NO_CHANGE:
        return True
    return _backfill_is_stale(function_change.backfill)


def _backfill_is_stale(backfill: BackfillResult) -> bool:
    return backfill.action != BackfillAction.WARN_ONLY
