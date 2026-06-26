"""Pure graph identity resolution helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from sqlbuild.compiler.planner.models import GraphIdentityNode, GraphNodeKey


def build_expected_graph_identity_hashes(
    *,
    nodes: Mapping[GraphNodeKey, GraphIdentityNode],
    execution_order: tuple[GraphNodeKey, ...],
    compose_identity: Callable[[str, tuple[tuple[GraphNodeKey, str], ...]], str],
) -> dict[GraphNodeKey, str | None]:
    hashes: dict[GraphNodeKey, str | None] = {}

    def resolve(key: GraphNodeKey, visiting: frozenset[GraphNodeKey]) -> str | None:
        if key in hashes:
            return hashes[key]
        node: GraphIdentityNode | None = nodes.get(key)
        if node is None or node.local_hash is None:
            hashes[key] = None
            return None
        if key in visiting:
            hashes[key] = node.local_hash
            return node.local_hash
        upstream_hashes: list[tuple[GraphNodeKey, str]] = []
        upstream_key: GraphNodeKey
        for upstream_key in node.upstream_keys:
            upstream_hash: str | None = resolve(upstream_key, visiting | {key})
            if upstream_hash is not None:
                upstream_hashes.append((upstream_key, upstream_hash))
        hashes[key] = compose_identity(node.local_hash, tuple(upstream_hashes))
        return hashes[key]

    key: GraphNodeKey
    for key in execution_order:
        resolve(key, frozenset())
    return hashes


def build_graph_write_identity_hashes(
    *,
    nodes: Mapping[GraphNodeKey, GraphIdentityNode],
    execution_order: tuple[GraphNodeKey, ...],
    selected_keys: frozenset[GraphNodeKey],
    base_identity_hashes: Mapping[GraphNodeKey, str],
    compose_identity: Callable[[str, tuple[tuple[GraphNodeKey, str], ...]], str],
) -> dict[GraphNodeKey, str]:
    hashes: dict[GraphNodeKey, str] = dict(base_identity_hashes)
    resolved_selected: dict[GraphNodeKey, str] = {}

    def resolve(key: GraphNodeKey, visiting: frozenset[GraphNodeKey]) -> str | None:
        if key not in selected_keys:
            return hashes.get(key)
        if key in resolved_selected:
            return resolved_selected[key]
        node: GraphIdentityNode | None = nodes.get(key)
        if node is None or node.local_hash is None:
            return hashes.get(key)
        if key in visiting:
            return node.local_hash
        upstream_hashes: list[tuple[GraphNodeKey, str]] = []
        upstream_key: GraphNodeKey
        for upstream_key in node.upstream_keys:
            upstream_hash: str | None = resolve(upstream_key, visiting | {key})
            if upstream_hash is not None:
                upstream_hashes.append((upstream_key, upstream_hash))
        composed: str = compose_identity(node.local_hash, tuple(upstream_hashes))
        resolved_selected[key] = composed
        hashes[key] = composed
        return composed

    key: GraphNodeKey
    for key in execution_order:
        resolve(key, frozenset())
    return hashes
