"""Lineage output formatting."""

from __future__ import annotations

import json
from collections.abc import Callable

from sqlbuild.cli.commands.main.helpers.lineage.models import (
    ColumnLineageTrace,
    LineageGraph,
    LineageNode,
)
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.models import ColumnLineageEdge, QualifiedLineageColumn
from sqlbuild.shared.helpers.colors import blue_bold, bold, dim

_HUMAN_COLUMN_TRACE_LIMIT: int = 25


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


def format_column_lineage_json(trace: ColumnLineageTrace) -> str:
    """Serialize column lineage trace as stable JSON."""

    payload: dict[str, object] = {
        "target": _serialize_column(trace.target),
        "direction": trace.direction,
        "trace": [_serialize_column_edge(edge) for edge in trace.trace],
    }
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


def format_column_lineage_list(
    trace: ColumnLineageTrace,
    *,
    use_color: bool = True,
) -> str:
    """Format column lineage as a flat dependency list."""

    if not trace.trace:
        return f"Column dependencies\n\n{_format_column(trace.target, use_color=use_color)}"
    displayed_trace: tuple[ColumnLineageEdge, ...] = trace.trace[:_HUMAN_COLUMN_TRACE_LIMIT]
    left_width: int = max(len(_column_id(edge.source)) for edge in displayed_trace)
    right_width: int = max(len(_column_id(edge.target)) for edge in displayed_trace)
    lines: list[str] = [_style("Column dependencies", blue_bold, use_color=use_color), ""]
    lines.extend(
        f"{_format_column(edge.source, use_color=use_color)}"
        f"{' ' * (left_width - len(_column_id(edge.source)))} "
        f"{_style('->', dim, use_color=use_color)} "
        f"{_format_column(edge.target, use_color=use_color)}"
        f"{' ' * (right_width - len(_column_id(edge.target)))} "
        f"{_format_transform(edge, use_color=use_color)}"
        for edge in displayed_trace
    )
    lines.extend(_format_column_trace_limit_note(trace, use_color=use_color))
    return "\n".join(lines)


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


def format_column_lineage_tree(
    trace: ColumnLineageTrace,
    *,
    use_color: bool = True,
) -> str:
    """Format column lineage for humans without graph implementation terms."""

    title: str = _style("Column trace", blue_bold, use_color=use_color)
    direction: str = _style(trace.direction, dim, use_color=use_color)
    lines: list[str] = [
        f"{title}  {_format_column(trace.target, use_color=use_color)}  {direction}",
        "",
    ]
    if not trace.trace:
        lines.append(_style("  No column dependencies found", dim, use_color=use_color))
        return "\n".join(lines)
    if trace.direction == "downstream":
        deps: dict[str, list[ColumnLineageEdge]] = {}
        for edge in trace.trace[:_HUMAN_COLUMN_TRACE_LIMIT]:
            deps.setdefault(_column_id(edge.source), []).append(edge)
        lines.extend(
            _format_column_trace_branch(
                trace.target,
                deps,
                direction="downstream",
                prefix="",
                seen={_column_id(trace.target)},
                use_color=use_color,
            )
        )
    else:
        deps = {}
        for edge in trace.trace[:_HUMAN_COLUMN_TRACE_LIMIT]:
            deps.setdefault(_column_id(edge.target), []).append(edge)
        lines.extend(
            _format_column_trace_branch(
                trace.target,
                deps,
                direction="upstream",
                prefix="",
                seen={_column_id(trace.target)},
                use_color=use_color,
            )
        )
    lines.extend(_format_column_trace_limit_note(trace, use_color=use_color))
    return "\n".join(lines)


def _format_column_trace_branch(
    column: QualifiedLineageColumn,
    deps: dict[str, list[ColumnLineageEdge]],
    *,
    direction: str,
    prefix: str,
    seen: set[str],
    use_color: bool,
) -> list[str]:
    lines: list[str] = []
    edges: list[ColumnLineageEdge] = sorted(
        deps.get(_column_id(column), ()),
        key=lambda edge: _column_id(edge.target if direction == "downstream" else edge.source),
    )
    arrow: str = "->" if direction == "downstream" else "<-"
    for edge in edges:
        related_column: QualifiedLineageColumn = (
            edge.target if direction == "downstream" else edge.source
        )
        related_id: str = _column_id(related_column)
        suffix: str = (
            _style(" (already shown)", dim, use_color=use_color) if related_id in seen else ""
        )
        lines.append(
            f"{prefix}  {_style(arrow, dim, use_color=use_color)} "
            f"{_format_column(related_column, use_color=use_color)} "
            f"{_style(f'({_human_transform_label(edge)})', dim, use_color=use_color)}{suffix}"
        )
        if related_id in seen:
            continue
        lines.extend(
            _format_column_trace_branch(
                related_column,
                deps,
                direction=direction,
                prefix=prefix + "     ",
                seen=seen | {related_id},
                use_color=use_color,
            )
        )
    return lines


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


def _serialize_column_edge(edge: ColumnLineageEdge) -> dict[str, object]:
    return {
        "source": _serialize_column(edge.source),
        "target": _serialize_column(edge.target),
        "transform": str(edge.transform_kind),
        "confidence": str(edge.confidence),
    }


def _serialize_column(column: QualifiedLineageColumn) -> dict[str, object]:
    return {
        "resource_type": CompiledResourceType(column.resource_type).value,
        "resource_name": column.resource_name,
        "column_name": column.column_name,
    }


def _format_column_trace_limit_note(
    trace: ColumnLineageTrace,
    *,
    use_color: bool,
) -> list[str]:
    if len(trace.trace) <= _HUMAN_COLUMN_TRACE_LIMIT:
        return []
    return [
        "",
        _style(
            f"Showing {_HUMAN_COLUMN_TRACE_LIMIT} of {len(trace.trace)} columns.",
            dim,
            use_color=use_color,
        ),
        _style(
            "Use --depth 1 to show direct column dependencies only.",
            dim,
            use_color=use_color,
        ),
        _style("Use --format json for the full trace.", dim, use_color=use_color),
    ]


def _format_transform(edge: ColumnLineageEdge, *, use_color: bool) -> str:
    return _style(_human_transform_label(edge), dim, use_color=use_color)


def _human_transform_label(edge: ColumnLineageEdge) -> str:
    if str(edge.transform_kind) == "star":
        return "from SELECT *"
    return str(edge.transform_kind)


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


def _format_column(column: QualifiedLineageColumn, *, use_color: bool) -> str:
    return _style(_column_id(column), bold, use_color=use_color)


def _column_id(column: QualifiedLineageColumn) -> str:
    return f"{column.resource_name}.{column.column_name}"


def _node_id(key: CompiledObjectKey) -> str:
    return f"{key.resource_type}:{key.name}"


def _style(text: str, styler: Callable[[str], str], *, use_color: bool) -> str:
    if not use_color:
        return text
    return styler(text)
