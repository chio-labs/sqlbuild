"""Lineage output formatting."""

from __future__ import annotations

import json
from collections.abc import Callable

from sqlbuild.cli.commands.main.helpers.lineage.models import LineageGraph, LineageNode
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.shared.helpers.colors import blue_bold, bold, dim


def format_lineage_json(graph: LineageGraph) -> str:
    """Serialize lineage graph as stable JSON."""

    payload: dict[str, object] = {
        "nodes": [_serialize_node(node) for node in graph.nodes],
        "edges": [
            {"from": _node_id(upstream), "to": _node_id(downstream)}
            for upstream, downstream in graph.edges
        ],
    }
    if graph.focus_keys:
        payload["focus"] = [_node_id(key) for key in graph.focus_keys]
    if graph.direction is not None:
        payload["direction"] = graph.direction
    return json.dumps(payload, indent=2)


def format_lineage_list(graph: LineageGraph, *, use_color: bool = True) -> str:
    """Format lineage graph as an edge list."""

    if not graph.edges:
        return "\n".join(_format_key(node.key, use_color=use_color) for node in graph.nodes)
    left_width: int = max(len(_node_id(upstream)) for upstream, _downstream in graph.edges)
    return "\n".join(
        f"{_format_key(upstream, use_color=use_color)}"
        f"{' ' * (left_width - len(_node_id(upstream)))} "
        f"{_style('->', dim, use_color=use_color)} "
        f"{_format_key(downstream, use_color=use_color)}"
        for upstream, downstream in graph.edges
    )


def format_lineage_tree(graph: LineageGraph, *, use_color: bool = True) -> str:
    """Format lineage graph for humans."""

    if len(graph.focus_keys) != 1 or graph.direction is None:
        return _format_graph_summary(graph, use_color=use_color)
    focus: CompiledObjectKey = graph.focus_keys[0]
    node_by_key: dict[CompiledObjectKey, LineageNode] = {node.key: node for node in graph.nodes}
    title: str = _style("Lineage", blue_bold, use_color=use_color)
    direction: str = _style(graph.direction, dim, use_color=use_color)
    lines: list[str] = [
        f"{title}  {_format_node(node_by_key[focus], use_color=use_color)}  {direction}"
    ]
    if graph.direction in {"upstream", "both"}:
        upstream: dict[CompiledObjectKey, list[CompiledObjectKey]] = {}
        for parent, child in graph.edges:
            upstream.setdefault(child, []).append(parent)
        if graph.direction == "both":
            lines.append(_style("upstream", blue_bold, use_color=use_color))
        lines.extend(
            _format_branch(
                focus,
                upstream,
                node_by_key,
                prefix="",
                seen={focus},
                use_color=use_color,
            )
        )
    if graph.direction in {"downstream", "both"}:
        downstream: dict[CompiledObjectKey, list[CompiledObjectKey]] = {}
        for parent, child in graph.edges:
            downstream.setdefault(parent, []).append(child)
        if graph.direction == "both":
            lines.append(_style("downstream", blue_bold, use_color=use_color))
        lines.extend(
            _format_branch(
                focus,
                downstream,
                node_by_key,
                prefix="",
                seen={focus},
                use_color=use_color,
            )
        )
    return "\n".join(lines)


def _format_graph_summary(graph: LineageGraph, *, use_color: bool) -> str:
    title: str = _style("Lineage graph", blue_bold, use_color=use_color)
    counts: str = _style(
        f"({len(graph.nodes)} nodes, {len(graph.edges)} edges)", dim, use_color=use_color
    )
    lines: list[str] = [f"{title}  {counts}"]
    if graph.edges:
        lines.extend(
            f"{_style('  - ', dim, use_color=use_color)}"
            f"{_format_key(parent, use_color=use_color)} "
            f"{_style('->', dim, use_color=use_color)} "
            f"{_format_key(child, use_color=use_color)}"
            for parent, child in graph.edges
        )
    else:
        lines.extend(f"  {_format_node(node, use_color=use_color)}" for node in graph.nodes)
    return "\n".join(lines)


def _format_branch(
    key: CompiledObjectKey,
    deps: dict[CompiledObjectKey, list[CompiledObjectKey]],
    node_by_key: dict[CompiledObjectKey, LineageNode],
    *,
    prefix: str,
    seen: set[CompiledObjectKey],
    use_color: bool,
) -> list[str]:
    lines: list[str] = []
    children: list[CompiledObjectKey] = sorted(
        deps.get(key, ()), key=lambda k: (str(k.resource_type), k.name)
    )
    if not children:
        return lines
    for index, child in enumerate(children):
        is_last: bool = index == len(children) - 1
        branch: str = "└── " if is_last else "├── "
        child_prefix: str = "    " if is_last else "│   "
        suffix: str = _style(" (already shown)", dim, use_color=use_color) if child in seen else ""
        lines.append(
            f"{_style(prefix + branch, dim, use_color=use_color)}"
            f"{_format_node(node_by_key[child], use_color=use_color)}{suffix}"
        )
        if child in seen:
            continue
        lines.extend(
            _format_branch(
                child,
                deps,
                node_by_key,
                prefix=prefix + child_prefix,
                seen=seen | {child},
                use_color=use_color,
            )
        )
    return lines


def _serialize_node(node: LineageNode) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": _node_id(node.key),
        "name": node.key.name,
        "resource_type": str(node.key.resource_type),
    }
    if node.relative_path is not None:
        payload["relative_path"] = node.relative_path
    if node.qualified_name is not None:
        payload["qualified_name"] = node.qualified_name
    return payload


def _format_node(node: LineageNode, *, use_color: bool) -> str:
    parts: list[str] = [
        _style(str(node.key.resource_type), dim, use_color=use_color),
        _style(node.key.name, bold, use_color=use_color),
    ]
    if node.relative_path is not None:
        parts.append(_style(node.relative_path, dim, use_color=use_color))
    return "  ".join(parts)


def _format_key(key: CompiledObjectKey, *, use_color: bool) -> str:
    return (
        f"{_style(str(key.resource_type), dim, use_color=use_color)}:"
        f"{_style(key.name, bold, use_color=use_color)}"
    )


def _node_id(key: CompiledObjectKey) -> str:
    return f"{key.resource_type}:{key.name}"


def _style(text: str, styler: Callable[[str], str], *, use_color: bool) -> str:
    if not use_color:
        return text
    return styler(text)
