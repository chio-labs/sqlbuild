"""Pure graph identity resolution helpers."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.planner.models import GraphIdentityNode, GraphNodeKey
from sqlbuild.compiler.planner.types import GraphIdentityComposer


def build_expected_graph_identity_hashes(
    *,
    nodes: Mapping[GraphNodeKey, GraphIdentityNode],
    execution_order: tuple[GraphNodeKey, ...],
    compose_identity: GraphIdentityComposer,
) -> dict[GraphNodeKey, str | None]:
    hashes: dict[GraphNodeKey, str | None] = {}

    def resolve(
        *,
        key: GraphNodeKey,
        visiting: frozenset[GraphNodeKey],
        cache: dict[GraphNodeKey, str | None],
    ) -> tuple[str | None, dict[GraphNodeKey, str | None]]:
        if key in cache:
            return cache[key], cache
        node: GraphIdentityNode | None = nodes.get(key)
        if node is None or node.local_hash is None:
            return None, {**cache, key: None}
        if key in visiting:
            return node.local_hash, {**cache, key: node.local_hash}
        upstream_hashes: list[tuple[GraphNodeKey, str]] = []
        upstream_key: GraphNodeKey
        for upstream_key in node.upstream_keys:
            upstream_hash, cache = resolve(key=upstream_key, visiting=visiting | {key}, cache=cache)
            if upstream_hash is not None:
                upstream_hashes.append((upstream_key, upstream_hash))
        composed: str = compose_identity(
            local_hash=node.local_hash,
            upstream_hashes=tuple(upstream_hashes),
        )
        return composed, {**cache, key: composed}

    key: GraphNodeKey
    for key in execution_order:
        _, hashes = resolve(key=key, visiting=frozenset(), cache=hashes)
    return hashes


def build_graph_write_identity_hashes(
    *,
    nodes: Mapping[GraphNodeKey, GraphIdentityNode],
    execution_order: tuple[GraphNodeKey, ...],
    selected_keys: frozenset[GraphNodeKey],
    base_identity_hashes: Mapping[GraphNodeKey, str],
    compose_identity: GraphIdentityComposer,
) -> dict[GraphNodeKey, str]:
    hashes: dict[GraphNodeKey, str] = dict(base_identity_hashes)
    resolved_selected: dict[GraphNodeKey, str] = {}

    def resolve(
        *,
        key: GraphNodeKey,
        visiting: frozenset[GraphNodeKey],
        cache: dict[GraphNodeKey, str],
        selected_cache: dict[GraphNodeKey, str],
    ) -> tuple[str | None, dict[GraphNodeKey, str], dict[GraphNodeKey, str]]:
        if key not in selected_keys:
            return cache.get(key), cache, selected_cache
        if key in selected_cache:
            return selected_cache[key], cache, selected_cache
        node: GraphIdentityNode | None = nodes.get(key)
        if node is None or node.local_hash is None:
            return cache.get(key), cache, selected_cache
        if key in visiting:
            return node.local_hash, cache, selected_cache
        upstream_hashes: list[tuple[GraphNodeKey, str]] = []
        upstream_key: GraphNodeKey
        for upstream_key in node.upstream_keys:
            upstream_hash, cache, selected_cache = resolve(
                key=upstream_key,
                visiting=visiting | {key},
                cache=cache,
                selected_cache=selected_cache,
            )
            if upstream_hash is not None:
                upstream_hashes.append((upstream_key, upstream_hash))
        composed: str = compose_identity(
            local_hash=node.local_hash,
            upstream_hashes=tuple(upstream_hashes),
        )
        return composed, {**cache, key: composed}, {**selected_cache, key: composed}

    key: GraphNodeKey
    for key in execution_order:
        _, hashes, resolved_selected = resolve(
            key=key,
            visiting=frozenset(),
            cache=hashes,
            selected_cache=resolved_selected,
        )
    return hashes
