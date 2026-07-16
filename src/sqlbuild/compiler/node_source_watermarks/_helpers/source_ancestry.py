"""Source ancestry helpers for node source watermark analysis."""

from __future__ import annotations

from sqlbuild.compiler.node_source_watermarks.models import (
    WatermarkGraphKey,
    WatermarkGraphNode,
    WatermarkSourceAncestryMember,
)
from sqlbuild.compiler.node_source_watermarks.types import WatermarkGraphResourceKind


def build_watermark_source_ancestry(
    *,
    node_keys: frozenset[WatermarkGraphKey],
    upstream_deps: dict[WatermarkGraphKey, tuple[WatermarkGraphKey, ...]],
    nodes: dict[WatermarkGraphKey, WatermarkGraphNode],
) -> tuple[WatermarkSourceAncestryMember, ...]:
    """Resolve raw source ancestors for graph nodes."""

    members: set[WatermarkSourceAncestryMember] = set()
    node_key: WatermarkGraphKey
    for node_key in node_keys:
        source_key: WatermarkGraphKey
        for source_key in _sources_for_node(
            node_key=node_key,
            upstream_deps=upstream_deps,
            nodes=nodes,
        ):
            members.add(WatermarkSourceAncestryMember(node_key=node_key, source_key=source_key))
    return tuple(sorted(members, key=_source_ancestry_sort_key))


def _sources_for_node(
    *,
    node_key: WatermarkGraphKey,
    upstream_deps: dict[WatermarkGraphKey, tuple[WatermarkGraphKey, ...]],
    nodes: dict[WatermarkGraphKey, WatermarkGraphNode],
) -> frozenset[WatermarkGraphKey]:
    result: set[WatermarkGraphKey] = set()
    visited: set[WatermarkGraphKey] = set()
    stack: list[WatermarkGraphKey] = list(upstream_deps.get(node_key, ()))
    while stack:
        current_key: WatermarkGraphKey = stack.pop()
        if current_key in visited:
            continue
        visited.add(current_key)
        current_node: WatermarkGraphNode | None = nodes.get(current_key)
        if current_node is None:
            continue
        if current_node.resource_kind == WatermarkGraphResourceKind.SOURCE:
            result.add(current_key)
            continue
        stack.extend(upstream_deps.get(current_key, ()))
    return frozenset(result)


def _source_ancestry_sort_key(
    member: WatermarkSourceAncestryMember,
) -> tuple[str, str, str, str]:
    return (
        member.node_key.node_type,
        member.node_key.node_name,
        member.source_key.node_type,
        member.source_key.node_name,
    )
