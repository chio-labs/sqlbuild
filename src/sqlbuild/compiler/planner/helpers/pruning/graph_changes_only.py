"""Pure graph changes-only propagation helpers."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.planner.models import (
    GraphChangesOnlyPropagationInput,
    GraphChangesOnlyPropagationResult,
    GraphNodeKey,
)


def build_graph_changes_only_propagation(
    *,
    request: GraphChangesOnlyPropagationInput,
) -> GraphChangesOnlyPropagationResult:
    upstream_deps: Mapping[GraphNodeKey, tuple[GraphNodeKey, ...]] = request.upstream_deps
    model_keys: frozenset[GraphNodeKey] = request.model_keys
    selected_model_keys: frozenset[GraphNodeKey] = request.selected_model_keys
    current_model_keys: frozenset[GraphNodeKey] = request.current_model_keys
    run_model_keys: frozenset[GraphNodeKey] = request.run_model_keys
    version_mismatch_model_keys: frozenset[GraphNodeKey] = request.version_mismatch_model_keys
    run_parent_keys: frozenset[GraphNodeKey] | None = request.run_parent_keys
    selected_parent_keys: frozenset[GraphNodeKey] | None = request.selected_parent_keys
    identity_stale_model_keys: frozenset[GraphNodeKey] = request.identity_stale_model_keys
    changed_seed_keys: frozenset[GraphNodeKey] = request.changed_seed_keys
    changed_source_keys: frozenset[GraphNodeKey] = request.changed_source_keys
    blocked_source_keys: frozenset[GraphNodeKey] = request.blocked_source_keys
    blocked_model_keys: set[GraphNodeKey] = set()
    identity_stale_keys: set[GraphNodeKey] = set(identity_stale_model_keys & current_model_keys)
    source_changed_model_keys: set[GraphNodeKey] = set()
    seed_changed_model_keys: set[GraphNodeKey] = set()
    upstream_changed_model_keys: set[GraphNodeKey] = set()
    blocked_source_keys_by_model_key: dict[GraphNodeKey, tuple[GraphNodeKey, ...]] = {}

    model_key: GraphNodeKey
    for model_key in model_keys:
        upstream_closure: frozenset[GraphNodeKey] = _expand_upstream(
            key=model_key,
            upstream_deps=upstream_deps,
        )
        blocked_upstream_sources: tuple[GraphNodeKey, ...] = tuple(
            sorted(
                upstream_closure & blocked_source_keys,
                key=lambda key: (key.node_type, key.node_name),
            )
        )
        if blocked_upstream_sources:
            blocked_model_keys.add(model_key)
            blocked_source_keys_by_model_key[model_key] = blocked_upstream_sources
            continue
        if model_key in current_model_keys and upstream_closure & changed_source_keys:
            source_changed_model_keys.add(model_key)
            continue
        if model_key in current_model_keys and upstream_closure & changed_seed_keys:
            seed_changed_model_keys.add(model_key)
            continue

    effective_run_parent_keys: frozenset[GraphNodeKey] = run_parent_keys or run_model_keys
    effective_selected_parent_keys: frozenset[GraphNodeKey] = (
        selected_parent_keys or selected_model_keys
    )
    propagated_run_keys: set[GraphNodeKey] = set(run_model_keys) | identity_stale_keys
    propagated_run_keys.update(source_changed_model_keys | seed_changed_model_keys)
    changed: bool = True
    while changed:
        changed = False
        for model_key in sorted(
            selected_model_keys & current_model_keys,
            key=lambda key: (key.node_type, key.node_name),
        ):
            if model_key in propagated_run_keys or model_key in blocked_model_keys:
                continue
            direct_upstream: tuple[GraphNodeKey, ...] = upstream_deps.get(model_key, ())
            selected_upstream_parent_keys: frozenset[GraphNodeKey] = frozenset(
                key for key in direct_upstream if key in effective_selected_parent_keys
            )
            upstream_runs: bool = bool(
                selected_upstream_parent_keys & (propagated_run_keys | effective_run_parent_keys)
            )
            upstream_version_mismatch: bool = bool(selected_upstream_parent_keys) and (
                model_key in version_mismatch_model_keys
            )
            if upstream_runs or upstream_version_mismatch:
                propagated_run_keys.add(model_key)
                upstream_changed_model_keys.add(model_key)
                changed = True

    return GraphChangesOnlyPropagationResult(
        blocked_model_keys=frozenset(blocked_model_keys),
        identity_stale_model_keys=frozenset(identity_stale_keys),
        source_changed_model_keys=frozenset(source_changed_model_keys),
        seed_changed_model_keys=frozenset(seed_changed_model_keys),
        upstream_changed_model_keys=frozenset(upstream_changed_model_keys),
        blocked_source_keys_by_model_key=blocked_source_keys_by_model_key,
    )


def _expand_upstream(
    *, key: GraphNodeKey, upstream_deps: Mapping[GraphNodeKey, tuple[GraphNodeKey, ...]]
) -> frozenset[GraphNodeKey]:
    visited: set[GraphNodeKey] = set()
    stack: list[GraphNodeKey] = [key]
    while stack:
        current: GraphNodeKey = stack.pop()
        upstream_key: GraphNodeKey
        for upstream_key in upstream_deps.get(current, ()):
            if upstream_key in visited:
                continue
            visited.add(upstream_key)
            stack.append(upstream_key)
    return frozenset(visited)
