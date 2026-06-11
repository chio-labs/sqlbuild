"""Standard planner scope pruning helpers."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_SEED
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.helpers.version_staleness import (
    build_stale_model_names_from_version_identities,
)
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    CascadeResult,
    FunctionChangeResult,
    PlannerChangeResults,
    PlannerResolvedActions,
    PlannerScope,
    ResolvedModelAction,
    RunDespiteUnchangedPlanningResult,
)
from sqlbuild.compiler.planner.types import BackfillAction, ChangeKind, PlanReason
from sqlbuild.compiler.source_freshness.models import StandardSourceFreshnessPlanningResult


def prune_standard_unchanged_scope(
    *,
    scope: PlannerScope,
    changes: PlannerChangeResults,
    resolved_actions: PlannerResolvedActions,
    source_freshness: StandardSourceFreshnessPlanningResult | None = None,
    run_despite_unchanged: RunDespiteUnchangedPlanningResult | None = None,
    expected_version_hashes: dict[str, str] | None = None,
    expected_seed_version_hashes: dict[str, str] | None = None,
    built_seed_fingerprints: dict[str, Fingerprint] | None = None,
) -> PlannerScope:
    """Remove unchanged selected SQL nodes for standard stale-only planning."""

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
            elif _run_despite_unchanged_marks_model_stale(
                model_name=key.name,
                run_despite_unchanged=run_despite_unchanged,
            ):
                selected_keys.add(key)
            continue
        if key.resource_type == CompiledResourceType.FUNCTION:
            function_change: FunctionChangeResult | None = changes.functions.get(key.name)
            if function_change is not None and _function_action_is_stale(function_change):
                selected_keys.add(key)
            continue
        if key.resource_type == CompiledResourceType.SEED:
            if _seed_identity_is_stale(
                seed_name=key.name,
                expected_seed_version_hashes=expected_seed_version_hashes,
                built_seed_fingerprints=built_seed_fingerprints,
            ):
                selected_keys.add(key)
            continue
        selected_keys.add(key)
    return replace(scope, selected_keys=frozenset(selected_keys))


def build_standard_identity_stale_model_names(
    *,
    scope: PlannerScope,
    expected_version_hashes: dict[str, str],
    built_version_hashes: dict[str, str | None],
) -> frozenset[str]:
    """Return all model names whose standard built identity is missing or stale."""

    return frozenset(
        build_stale_model_names_from_version_identities(
            model_names=tuple(scope.models_by_name),
            expected_version_hashes=expected_version_hashes,
            built_version_hashes=built_version_hashes,
        )
    )


def mark_version_identity_stale_actions(
    *,
    scope: PlannerScope,
    resolved_actions: PlannerResolvedActions,
    expected_version_hashes: dict[str, str] | None,
) -> PlannerResolvedActions:
    """Mark standard composed-version stale entries as upstream-driven work."""

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


def mark_run_despite_unchanged_actions(
    *,
    scope: PlannerScope,
    resolved_actions: PlannerResolvedActions,
    run_despite_unchanged: RunDespiteUnchangedPlanningResult,
) -> PlannerResolvedActions:
    """Mark configured roots and propagated downstreams selected by runtime staleness."""

    if not run_despite_unchanged.stale_model_names:
        return resolved_actions
    models: dict[str, ResolvedModelAction] = dict(resolved_actions.models)
    key: CompiledObjectKey
    for key in scope.selected_keys:
        if key.resource_type != CompiledResourceType.MODEL:
            continue
        resolved_action: ResolvedModelAction | None = models.get(key.name)
        if resolved_action is None:
            continue
        if key.name in run_despite_unchanged.root_model_names:
            models[key.name] = replace(
                resolved_action,
                change=replace(
                    resolved_action.change,
                    change_kind=ChangeKind.RUN_DESPITE_UNCHANGED,
                ),
                backfill=BackfillResult(action=BackfillAction.FORWARD_ONLY),
            )
            continue
        root_cause: str | None = run_despite_unchanged.downstream_root_causes.get(key.name)
        if root_cause is None or resolved_action.cascade is not None:
            continue
        models[key.name] = replace(
            resolved_action,
            cascade=CascadeResult(
                effective_action=BackfillAction.FORWARD_ONLY,
                effective_duration=None,
                root_cause=root_cause,
                root_reason=PlanReason.RUN_DESPITE_UNCHANGED,
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


def _run_despite_unchanged_marks_model_stale(
    *,
    model_name: str,
    run_despite_unchanged: RunDespiteUnchangedPlanningResult | None,
) -> bool:
    if run_despite_unchanged is None:
        return False
    return model_name in run_despite_unchanged.stale_model_names


def _function_action_is_stale(function_change: FunctionChangeResult) -> bool:
    if function_change.reason != PlanReason.NO_CHANGE:
        return True
    return _backfill_is_stale(function_change.backfill)


def _seed_identity_is_stale(
    *,
    seed_name: str,
    expected_seed_version_hashes: dict[str, str] | None,
    built_seed_fingerprints: dict[str, Fingerprint] | None,
) -> bool:
    expected_hash: str | None = (expected_seed_version_hashes or {}).get(seed_name)
    if expected_hash is None:
        return True
    fingerprint: Fingerprint | None = (built_seed_fingerprints or {}).get(seed_name)
    if fingerprint is None or fingerprint.node_type != NODE_TYPE_SEED:
        return True
    return fingerprint.version_hash != expected_hash


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
    source_freshness: StandardSourceFreshnessPlanningResult | None,
) -> bool:
    if source_freshness is None or source_freshness.propagation is None:
        return False
    return model_name in source_freshness.propagation.stale_model_names


def _backfill_is_stale(backfill: BackfillResult) -> bool:
    return backfill.action != BackfillAction.FORWARD_ONLY
