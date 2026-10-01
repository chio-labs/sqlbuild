"""Pure graph identity resolution helpers."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.planner.classes.graph_identity_resolver import GraphIdentityResolver
from sqlbuild.compiler.planner.models import GraphIdentityNode, GraphNodeKey
from sqlbuild.compiler.planner.types import GraphIdentityComposer


def build_expected_graph_identity_hashes(
    *,
    nodes: Mapping[GraphNodeKey, GraphIdentityNode],
    execution_order: tuple[GraphNodeKey, ...],
    compose_identity: GraphIdentityComposer,
) -> dict[GraphNodeKey, str | None]:
    resolver: GraphIdentityResolver = GraphIdentityResolver(
        nodes=nodes, compose_identity=compose_identity, base_hashes={}, selected_keys=None
    )
    key: GraphNodeKey
    for key in execution_order:
        _ = resolver.resolve_expected(key)
    return resolver.hashes


def build_graph_write_identity_hashes(
    *,
    nodes: Mapping[GraphNodeKey, GraphIdentityNode],
    execution_order: tuple[GraphNodeKey, ...],
    selected_keys: frozenset[GraphNodeKey],
    base_identity_hashes: Mapping[GraphNodeKey, str],
    compose_identity: GraphIdentityComposer,
) -> dict[GraphNodeKey, str]:
    resolver: GraphIdentityResolver = GraphIdentityResolver(
        nodes=nodes,
        compose_identity=compose_identity,
        base_hashes=base_identity_hashes,
        selected_keys=selected_keys,
    )
    key: GraphNodeKey
    for key in execution_order:
        _ = resolver.resolve_write(key)
    return {hashed_key: value for hashed_key, value in resolver.hashes.items() if value is not None}
