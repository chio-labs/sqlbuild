"""Direct changes-only planner scope pruning helpers."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    CascadeResult,
    FunctionChangeResult,
    PlannerChangeResults,
    PlannerResolvedActions,
    PlannerScope,
    ResolvedModelAction,
)
from sqlbuild.compiler.planner.types import BackfillAction, ChangeKind, PlanReason
from sqlbuild.compiler.source_freshness.models import DirectSourceFreshnessPlanningResult


def prune_unchanged_scope(
    *,
    scope: PlannerScope,
    changes: PlannerChangeResults,
    resolved_actions: PlannerResolvedActions,
    source_freshness: DirectSourceFreshnessPlanningResult | None = None,
    expected_version_hashes: dict[str, str] | None = None,
) -> PlannerScope:
    """Remove unchanged selected SQL nodes for direct changes-only planning."""

    selected_keys: set[CompiledObjectKey] = set()
    key: CompiledObjectKey
    for key in scope.selected_keys:
        if key.resource_type == CompiledResourceType.MODEL:
            resolved_action: ResolvedModelAction | None = resolved_actions.models.get(key.name)
            if resolved_action is not None and _model_action_is_stale(resolved_action):
                selected_keys.add(key)
            elif _model_version_identity_is_stale(
                model_name=key.name,
                expected_version_hashes=expected_version_hashes,
                resolved_action=resolved_action,
            ):
                selected_keys.add(key)
            elif _source_freshness_marks_model_stale(
                model_name=key.name,
                source_freshness=source_freshness,
            ):
                selected_keys.add(key)
            continue
        if key.resource_type == CompiledResourceType.FUNCTION:
            function_change: FunctionChangeResult | None = changes.functions.get(key.name)
            if function_change is not None and _function_action_is_stale(function_change):
                selected_keys.add(key)
            continue
        selected_keys.add(key)
    return replace(scope, selected_keys=frozenset(selected_keys))


def build_direct_identity_stale_model_names(
    *,
    scope: PlannerScope,
    expected_version_hashes: dict[str, str],
    built_version_hashes: dict[str, str | None],
) -> frozenset[str]:
    """Return all model names whose direct built identity is missing or stale."""

    stale_model_names: set[str] = set()
    model_name: str
    for model_name in scope.models_by_name:
        expected_version_hash: str | None = expected_version_hashes.get(model_name)
        if expected_version_hash is None:
            continue
        built_version_hash: str | None = built_version_hashes.get(model_name)
        if built_version_hash != expected_version_hash:
            stale_model_names.add(model_name)
    return frozenset(stale_model_names)


def mark_version_identity_stale_actions(
    *,
    scope: PlannerScope,
    resolved_actions: PlannerResolvedActions,
    expected_version_hashes: dict[str, str] | None,
) -> PlannerResolvedActions:
    """Mark direct composed-version stale entries as upstream-driven work."""

    if expected_version_hashes is None:
        return resolved_actions
    models: dict[str, ResolvedModelAction] = dict(resolved_actions.models)
    key: CompiledObjectKey
    for key in scope.selected_keys:
        if key.resource_type != CompiledResourceType.MODEL:
            continue
        resolved_action: ResolvedModelAction | None = models.get(key.name)
        if resolved_action is None:
            continue
        if not _version_identity_requires_upstream_cascade(
            model_name=key.name,
            expected_version_hashes=expected_version_hashes,
            resolved_action=resolved_action,
        ):
            continue
        models[key.name] = replace(
            resolved_action,
            cascade=CascadeResult(
                effective_action=BackfillAction.FORWARD_ONLY,
                effective_duration=None,
                root_cause=None,
            ),
        )
    return PlannerResolvedActions(models=models)


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


def _model_version_identity_is_stale(
    *,
    model_name: str,
    expected_version_hashes: dict[str, str] | None,
    resolved_action: ResolvedModelAction | None,
) -> bool:
    if resolved_action is None or expected_version_hashes is None:
        return False
    expected_version_hash: str | None = expected_version_hashes.get(model_name)
    if expected_version_hash is None:
        return False
    previous_version_hash: str | None = resolved_action.change.previous_version_hash
    if previous_version_hash is None:
        return True
    return previous_version_hash != expected_version_hash


def _version_identity_requires_upstream_cascade(
    *,
    model_name: str,
    expected_version_hashes: dict[str, str],
    resolved_action: ResolvedModelAction,
) -> bool:
    if resolved_action.change.change_kind != ChangeKind.NO_CHANGE:
        return False
    if resolved_action.cascade is not None:
        return False
    if _backfill_is_stale(resolved_action.backfill):
        return False
    return _model_version_identity_is_stale(
        model_name=model_name,
        expected_version_hashes=expected_version_hashes,
        resolved_action=resolved_action,
    )


def _source_freshness_marks_model_stale(
    *,
    model_name: str,
    source_freshness: DirectSourceFreshnessPlanningResult | None,
) -> bool:
    if source_freshness is None or source_freshness.propagation is None:
        return False
    return model_name in source_freshness.propagation.stale_model_names


def _backfill_is_stale(backfill: BackfillResult) -> bool:
    return backfill.action != BackfillAction.FORWARD_ONLY
