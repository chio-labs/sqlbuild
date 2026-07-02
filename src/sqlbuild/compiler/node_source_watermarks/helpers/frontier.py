"""Frontier resolution helpers for node source watermark analysis."""

from __future__ import annotations

from sqlbuild.compiler.node_source_watermarks.models import (
    WatermarkFrontierMember,
    WatermarkGraphKey,
    WatermarkGraphNode,
)
from sqlbuild.compiler.node_source_watermarks.types import WatermarkGraphResourceKind


def build_materialized_watermark_frontier(
    *,
    root_keys: frozenset[WatermarkGraphKey],
    upstream_deps: dict[WatermarkGraphKey, tuple[WatermarkGraphKey, ...]],
    nodes: dict[WatermarkGraphKey, WatermarkGraphNode],
) -> tuple[WatermarkFrontierMember, ...]:
    """Resolve first materialized/source frontier nodes for selected roots."""

    members: set[WatermarkFrontierMember] = set()
    root_key: WatermarkGraphKey
    for root_key in root_keys:
        frontier_key: WatermarkGraphKey
        for frontier_key in _frontier_for_root(
            root_key=root_key,
            upstream_deps=upstream_deps,
            nodes=nodes,
        ):
            members.add(WatermarkFrontierMember(root_key=root_key, frontier_key=frontier_key))
    return tuple(sorted(members, key=_frontier_member_sort_key))


def _frontier_for_root(
    *,
    root_key: WatermarkGraphKey,
    upstream_deps: dict[WatermarkGraphKey, tuple[WatermarkGraphKey, ...]],
    nodes: dict[WatermarkGraphKey, WatermarkGraphNode],
) -> frozenset[WatermarkGraphKey]:
    result: set[WatermarkGraphKey] = set()
    visited: set[WatermarkGraphKey] = set()
    stack: list[WatermarkGraphKey] = list(upstream_deps.get(root_key, ()))
    while stack:
        current_key: WatermarkGraphKey = stack.pop()
        if current_key in visited:
            continue
        visited.add(current_key)
        current_node: WatermarkGraphNode | None = nodes.get(current_key)
        if current_node is None:
            continue
        if _is_frontier_node(current_node):
            result.add(current_key)
            continue
        stack.extend(upstream_deps.get(current_key, ()))
    return frozenset(result)


def _is_frontier_node(node: WatermarkGraphNode) -> bool:
    if node.resource_kind == WatermarkGraphResourceKind.SOURCE:
        return True
    return node.materialized


def _frontier_member_sort_key(member: WatermarkFrontierMember) -> tuple[str, str, str, str]:
    return (
        member.root_key.node_type,
        member.root_key.node_name,
        member.frontier_key.node_type,
        member.frontier_key.node_name,
    )
