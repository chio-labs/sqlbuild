"""Mixed dbt/SQLBuild lineage output formatting."""

from __future__ import annotations

import json

from sqlbuild.integrations.dbt.models import DbtCombinedGraphKey, DbtLineageGraph, DbtLineageNode
from sqlbuild.integrations.dbt.types import DbtLineageDirection
from sqlbuild.shared.helpers.cli_style import CliStyle


def format_dbt_lineage_json(graph: DbtLineageGraph) -> str:
    """Serialize mixed dbt/SQLBuild lineage graph as stable JSON."""

    payload: dict[str, object] = {
        "nodes": [_serialize_node(node) for node in graph.nodes],
        "edges": [
            {"from": upstream.stable_id, "to": downstream.stable_id}
            for upstream, downstream in graph.edges
        ],
    }
    if graph.focus_keys:
        payload["focus"] = [key.stable_id for key in graph.focus_keys]
    if graph.direction is not None:
        payload["direction"] = graph.direction.value
    return json.dumps(payload, indent=2)


def format_dbt_lineage_list(graph: DbtLineageGraph, *, use_color: bool = True) -> str:
    """Format mixed dbt/SQLBuild lineage graph as an edge list."""

    style: CliStyle = CliStyle(use_color=use_color)
    node_by_key: dict[DbtCombinedGraphKey, DbtLineageNode] = {
        node.key: node for node in graph.nodes
    }
    if not graph.edges:
        return "\n".join(_format_node(node, style=style) for node in graph.nodes)
    left_width: int = max(len(upstream.stable_id) for upstream, _downstream in graph.edges)
    return "\n".join(
        f"{_format_node(node_by_key[upstream], style=style)}"
        f"{' ' * (left_width - len(upstream.stable_id))} "
        f"{style.muted('->')} "
        f"{_format_node(node_by_key[downstream], style=style)}"
        for upstream, downstream in graph.edges
    )


def format_dbt_lineage_tree(graph: DbtLineageGraph, *, use_color: bool = True) -> str:
    """Format mixed dbt/SQLBuild lineage graph for humans."""

    if len(graph.focus_keys) != 1 or graph.direction is None:
        return _format_graph_summary(graph=graph, use_color=use_color)
    style: CliStyle = CliStyle(use_color=use_color)
    focus: DbtCombinedGraphKey = graph.focus_keys[0]
    node_by_key: dict[DbtCombinedGraphKey, DbtLineageNode] = {
        node.key: node for node in graph.nodes
    }
    lines: list[str] = [
        f"{style.object_name('Lineage')}  {_format_node(node_by_key[focus], style=style)}  "
        f"{style.muted(graph.direction.value)}"
    ]
    if graph.direction in {DbtLineageDirection.UPSTREAM, DbtLineageDirection.BOTH}:
        upstream: dict[DbtCombinedGraphKey, list[DbtCombinedGraphKey]] = {}
        for parent, child in graph.edges:
            upstream.setdefault(child, []).append(parent)
        if graph.direction == DbtLineageDirection.BOTH:
            lines.append(style.object_name("upstream"))
        lines.extend(
            _format_branch(
                focus,
                upstream,
                node_by_key,
                prefix="",
                seen={focus},
                style=style,
            )
        )
    if graph.direction in {DbtLineageDirection.DOWNSTREAM, DbtLineageDirection.BOTH}:
        downstream: dict[DbtCombinedGraphKey, list[DbtCombinedGraphKey]] = {}
        for parent, child in graph.edges:
            downstream.setdefault(parent, []).append(child)
        if graph.direction == DbtLineageDirection.BOTH:
            lines.append(style.object_name("downstream"))
        lines.extend(
            _format_branch(
                focus,
                downstream,
                node_by_key,
                prefix="",
                seen={focus},
                style=style,
            )
        )
    return "\n".join(lines)


def _serialize_node(node: DbtLineageNode) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": node.key.stable_id,
        "owner": node.key.owner.value,
        "resource_type": node.key.resource_type.value,
        "name": node.key.name,
        "label": node.label,
    }
    if node.qualified_name is not None:
        payload["qualified_name"] = node.qualified_name
    if node.relative_path is not None:
        payload["relative_path"] = node.relative_path
    return payload


def _format_node(node: DbtLineageNode, *, style: CliStyle) -> str:
    owner_prefix: str = f"{node.key.owner.value}:"
    return style.object_name(f"{owner_prefix}{node.label}")


def _format_branch(
    key: DbtCombinedGraphKey,
    deps: dict[DbtCombinedGraphKey, list[DbtCombinedGraphKey]],
    node_by_key: dict[DbtCombinedGraphKey, DbtLineageNode],
    *,
    prefix: str,
    seen: set[DbtCombinedGraphKey],
    style: CliStyle,
) -> list[str]:
    lines: list[str] = []
    children: list[DbtCombinedGraphKey] = sorted(
        deps.get(key, ()), key=lambda child: child.stable_id
    )
    for index, child in enumerate(children):
        is_last: bool = index == len(children) - 1
        branch: str = "`-" if is_last else "+-"
        continuation: str = "  " if is_last else "| "
        suffix: str = style.muted(" (already shown)") if child in seen else ""
        lines.append(
            f"{prefix}{style.muted(branch)} {_format_node(node_by_key[child], style=style)}{suffix}"
        )
        if child in seen:
            continue
        lines.extend(
            _format_branch(
                child,
                deps,
                node_by_key,
                prefix=prefix + continuation,
                seen=seen | {child},
                style=style,
            )
        )
    return lines


def _format_graph_summary(*, graph: DbtLineageGraph, use_color: bool) -> str:
    style: CliStyle = CliStyle(use_color=use_color)
    lines: list[str] = [style.object_name("Lineage graph")]
    if graph.nodes:
        lines.append("")
        lines.extend(_format_node(node, style=style) for node in graph.nodes)
    return "\n".join(lines)
