"""Standard planner scope pruning helpers."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_SEED
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner._helpers.graph.selectors import expand_required_build_resources
from sqlbuild.compiler.planner._helpers.identity.hashing import (
    graph_key_for_compiled_resource,
)
from sqlbuild.compiler.planner._helpers.pruning.version_staleness import (
    build_stale_model_names_from_version_identities,
)
from sqlbuild.compiler.planner.main.planning.graph_changes_only import (
    build_graph_changes_only_propagation,
)
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    CascadeResult,
    FunctionChangeResult,
    GraphChangesOnlyPropagationInput,
    GraphChangesOnlyPropagationResult,
    GraphNodeKey,
    PlannerChangeResults,
    PlannerResolvedActions,
    PlannerScope,
    ResolvedModelAction,
    RunDespiteUnchangedPlanningResult,
)
from sqlbuild.compiler.planner.types import BackfillAction, ChangeKind, PlanReason
from sqlbuild.compiler.source_freshness.models import StandardSourceFreshnessPlanningResult

_RUN_PARENT_TYPES: frozenset[CompiledResourceType] = frozenset(
    {
        CompiledResourceType.MODEL,
        CompiledResourceType.SEED,
    }
)


def prune_standard_unchanged_scope(
    *,
    scope: PlannerScope,
    changes: PlannerChangeResults,
    resolved_actions: PlannerResolvedActions,
    source_freshness: StandardSourceFreshnessPlanningResult | None = None,
    run_despite_unchanged: RunDespiteUnchangedPlanningResult | None = None,
    forced_stale_model_names: tuple[str, ...] = (),
    expected_version_hashes: dict[str, str] | None = None,
    expected_seed_version_hashes: dict[str, str] | None = None,
    built_seed_fingerprints: dict[str, Fingerprint] | None = None,
) -> PlannerScope:
    """Remove unchanged selected SQL nodes for standard stale-only planning."""

    selected_keys: set[CompiledObjectKey] = set()
    identity_scope_keys: frozenset[CompiledObjectKey] = (
        scope.user_selected_keys or scope.selected_keys
    )
    forced_stale: frozenset[str] = frozenset(forced_stale_model_names)
    identity_stale_keys: frozenset[CompiledObjectKey] = frozenset(
        key
        for key in scope.selected_keys
        if key.resource_type == CompiledResourceType.MODEL
        and _model_version_identity_is_stale(
            model_name=key.name,
            expected_version_hashes=expected_version_hashes,
            resolved_action=resolved_actions.models.get(key.name),
        )
        and _upstream_identity_scope_is_complete(
            key=key,
            selected_keys=identity_scope_keys,
            upstream_deps=scope.upstream_deps,
        )
    )
    key: CompiledObjectKey
    for key in scope.selected_keys:
        if key.resource_type == CompiledResourceType.MODEL:
            resolved_action: ResolvedModelAction | None = resolved_actions.models.get(key.name)
            if resolved_action is not None and _model_action_is_stale(resolved_action):
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
            elif key.name in forced_stale:
                selected_keys.add(key)
            continue
        if key.resource_type in {CompiledResourceType.UDF, CompiledResourceType.TABLE_FN}:
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
    pruned_selected_keys: frozenset[CompiledObjectKey] = _add_neutral_propagated_model_keys(
        scope=scope,
        original_selected_keys=identity_scope_keys,
        selected_keys=frozenset(selected_keys),
        identity_stale_keys=identity_stale_keys,
    )
    return replace(
        scope,
        selected_keys=expand_required_build_resources(
            selected_keys=pruned_selected_keys,
            upstream=scope.upstream_deps,
            downstream=scope.downstream_deps,
            include_upstream_functions=True,
            include_upstream_seeds=False,
            include_downstream_functions=False,
        ),
    )


def mark_direct_parent_run_actions(
    *, scope: PlannerScope, resolved_actions: PlannerResolvedActions
) -> PlannerResolvedActions:
    """Mark unchanged selected models that run because a direct parent runs."""

    models: dict[str, ResolvedModelAction] = dict(resolved_actions.models)
    run_parent_keys: frozenset[CompiledObjectKey] = frozenset(
        key for key in scope.selected_keys if key.resource_type in _RUN_PARENT_TYPES
    )
    propagation: GraphChangesOnlyPropagationResult = build_graph_changes_only_propagation(
        request=GraphChangesOnlyPropagationInput(
            upstream_deps=_neutral_upstream_deps(scope=scope),
            model_keys=_neutral_model_keys(scope=scope, keys=scope.selected_keys),
            selected_model_keys=_neutral_model_keys(scope=scope, keys=scope.selected_keys),
            current_model_keys=frozenset(
                _graph_key(key)
                for key in scope.selected_keys
                if key.resource_type == CompiledResourceType.MODEL
                and (resolved := models.get(key.name)) is not None
                and _can_mark_upstream_cascade(resolved)
            ),
            run_model_keys=frozenset(
                _graph_key(key)
                for key in run_parent_keys
                if key.resource_type == CompiledResourceType.MODEL
                and (resolved := models.get(key.name)) is not None
                and not _can_mark_upstream_cascade(resolved)
            ),
            run_parent_keys=frozenset(_graph_key(key) for key in run_parent_keys),
            selected_parent_keys=frozenset(_graph_key(key) for key in scope.selected_keys),
            version_mismatch_model_keys=frozenset(),
        )
    )
    key: CompiledObjectKey
    for key in scope.selected_keys:
        if key.resource_type != CompiledResourceType.MODEL:
            continue
        resolved_action: ResolvedModelAction | None = models.get(key.name)
        if resolved_action is None or not _can_mark_upstream_cascade(resolved_action):
            continue
        if _graph_key(key) not in propagation.upstream_changed_model_keys:
            continue
        upstream_key: CompiledObjectKey
        for upstream_key in scope.upstream_deps.get(key, ()):
            if upstream_key in run_parent_keys:
                models[key.name] = replace(
                    resolved_action,
                    cascade=CascadeResult(
                        effective_action=BackfillAction.FORWARD_ONLY,
                        effective_duration=None,
                        root_cause=upstream_key.name,
                        root_reason=PlanReason.UPSTREAM_CHANGED,
                    ),
                )
                break
    return PlannerResolvedActions(models=models)


def _add_neutral_propagated_model_keys(
    *,
    scope: PlannerScope,
    original_selected_keys: frozenset[CompiledObjectKey],
    selected_keys: frozenset[CompiledObjectKey],
    identity_stale_keys: frozenset[CompiledObjectKey],
) -> frozenset[CompiledObjectKey]:
    propagation: GraphChangesOnlyPropagationResult = build_graph_changes_only_propagation(
        request=GraphChangesOnlyPropagationInput(
            upstream_deps=_neutral_upstream_deps(scope=scope),
            model_keys=_neutral_model_keys(scope=scope, keys=scope.selected_keys),
            selected_model_keys=_neutral_model_keys(scope=scope, keys=original_selected_keys),
            current_model_keys=frozenset(
                _graph_key(key)
                for key in original_selected_keys
                if key.resource_type == CompiledResourceType.MODEL and key not in selected_keys
            ),
            run_model_keys=frozenset(
                _graph_key(key)
                for key in selected_keys
                if key.resource_type == CompiledResourceType.MODEL
            ),
            run_parent_keys=frozenset(
                _graph_key(key) for key in selected_keys if key.resource_type in _RUN_PARENT_TYPES
            ),
            selected_parent_keys=frozenset(
                _graph_key(key)
                for key in original_selected_keys
                if key.resource_type in _RUN_PARENT_TYPES
            ),
            identity_stale_model_keys=frozenset(_graph_key(key) for key in identity_stale_keys),
            version_mismatch_model_keys=frozenset(_graph_key(key) for key in identity_stale_keys),
        )
    )
    expanded: set[CompiledObjectKey] = set(selected_keys) | set(identity_stale_keys)
    upstream_changed_keys: frozenset[GraphNodeKey] = propagation.upstream_changed_model_keys
    key: CompiledObjectKey
    for key in original_selected_keys:
        if (
            key.resource_type == CompiledResourceType.MODEL
            and _graph_key(key) in upstream_changed_keys
        ):
            expanded.add(key)
    return frozenset(expanded)


def _neutral_upstream_deps(*, scope: PlannerScope) -> dict[GraphNodeKey, tuple[GraphNodeKey, ...]]:
    neutral_deps: dict[GraphNodeKey, tuple[GraphNodeKey, ...]] = {}
    for key, upstream_keys in scope.upstream_deps.items():
        neutral_upstreams: list[GraphNodeKey] = []
        for upstream_key in upstream_keys:
            neutral_upstreams.append(_graph_key(upstream_key))
        neutral_deps[_graph_key(key)] = tuple(neutral_upstreams)
    return neutral_deps


def _neutral_model_keys(
    *, scope: PlannerScope, keys: frozenset[CompiledObjectKey]
) -> frozenset[GraphNodeKey]:
    return frozenset(
        _graph_key(key) for key in keys if key.resource_type == CompiledResourceType.MODEL
    )


def _graph_key(key: CompiledObjectKey) -> GraphNodeKey:
    return graph_key_for_compiled_resource(resource_type=key.resource_type, name=key.name)


def build_standard_identity_stale_model_names(
    *,
    scope: PlannerScope,
    expected_version_hashes: dict[str, str],
    built_version_hashes: dict[str, str | None],
    forced_stale_model_names: tuple[str, ...] = (),
) -> frozenset[str]:
    """Return all model names whose standard built identity is missing or stale."""

    return frozenset(
        build_stale_model_names_from_version_identities(
            model_names=tuple(scope.models_by_name),
            expected_version_hashes=expected_version_hashes,
            built_version_hashes=built_version_hashes,
            forced_stale_model_names=forced_stale_model_names,
        )
    )


def mark_version_identity_stale_actions(
    *,
    scope: PlannerScope,
    resolved_actions: PlannerResolvedActions,
    expected_version_hashes: dict[str, str] | None,
    forced_stale_model_names: tuple[str, ...] = (),
) -> PlannerResolvedActions:
    """Mark standard composed-version stale entries as upstream-driven work."""

    if expected_version_hashes is None:
        return resolved_actions
    models: dict[str, ResolvedModelAction] = dict(resolved_actions.models)
    forced_stale: frozenset[str] = frozenset(forced_stale_model_names)
    key: CompiledObjectKey
    for key in scope.selected_keys:
        if key.resource_type != CompiledResourceType.MODEL:
            continue
        resolved_action: ResolvedModelAction | None = models.get(key.name)
        if resolved_action is None:
            continue
        if key.name in forced_stale and _can_mark_upstream_cascade(resolved_action):
            models[key.name] = replace(
                resolved_action,
                cascade=CascadeResult(
                    effective_action=BackfillAction.FORWARD_ONLY,
                    effective_duration=None,
                    root_cause=None,
                    root_reason=PlanReason.UPSTREAM_CHANGED,
                ),
            )
            continue
    return PlannerResolvedActions(models=models)


def _can_mark_upstream_cascade(resolved_action: ResolvedModelAction) -> bool:
    if resolved_action.change.change_kind != ChangeKind.NO_CHANGE:
        return False
    if resolved_action.cascade is not None:
        return False
    return not _backfill_is_stale(resolved_action.backfill)


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


def _upstream_identity_scope_is_complete(
    *,
    key: CompiledObjectKey,
    selected_keys: frozenset[CompiledObjectKey],
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> bool:
    visited: set[CompiledObjectKey] = set()

    def visit(
        *, upstream_key: CompiledObjectKey, seen: set[CompiledObjectKey]
    ) -> tuple[bool, set[CompiledObjectKey]]:
        if upstream_key in seen:
            return True, seen
        seen = seen | {upstream_key}
        if upstream_key.resource_type in _RUN_PARENT_TYPES and upstream_key not in selected_keys:
            return False, seen
        for parent_key in upstream_deps.get(upstream_key, ()):
            complete, seen = visit(upstream_key=parent_key, seen=seen)
            if not complete:
                return False, seen
        return True, seen

    for upstream_key in upstream_deps.get(key, ()):
        complete, visited = visit(upstream_key=upstream_key, seen=visited)
        if not complete:
            return False
    return True


def _source_freshness_marks_model_stale(
    *,
    model_name: str,
    source_freshness: StandardSourceFreshnessPlanningResult | None,
) -> bool:
    if source_freshness is None or source_freshness.propagation is None:
        return False
    return model_name in (
        source_freshness.propagation.stale_model_names
        | source_freshness.propagation.blocked_model_names
    )


def _backfill_is_stale(backfill: BackfillResult) -> bool:
    return backfill.action != BackfillAction.FORWARD_ONLY
