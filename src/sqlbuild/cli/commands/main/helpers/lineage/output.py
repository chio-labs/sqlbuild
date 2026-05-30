"""Lineage output formatting."""

from __future__ import annotations

import json

from sqlbuild.cli.commands.main.helpers.lineage.models import (
    ColumnLineageTrace,
    LineageGraph,
    LineageNode,
)
from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.models import ColumnLineageEdge, QualifiedLineageColumn
from sqlbuild.shared.helpers.cli_style import CliStyle

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
        "metadata": {
            "mode": trace.mode.value,
            "max_depth": trace.max_depth,
            "analyzed_models": trace.analyzed_model_count,
            "truncated": trace.truncated,
        },
        "trace": [_serialize_column_edge(edge) for edge in trace.trace],
    }
    return json.dumps(payload, indent=2)


def format_lineage_list(graph: LineageGraph, *, use_color: bool = True) -> str:
    """Format lineage graph as an edge list."""

    style: CliStyle = CliStyle(use_color=use_color)
    if not graph.edges:
        return "\n".join(_format_key(node.key, style=style) for node in graph.nodes)
    left_width: int = max(len(_node_id(upstream)) for upstream, _downstream in graph.edges)
    return "\n".join(
        f"{_format_key(upstream, style=style)}"
        f"{' ' * (left_width - len(_node_id(upstream)))} "
        f"{style.muted('->')} "
        f"{_format_key(downstream, style=style)}"
        for upstream, downstream in graph.edges
    )


def format_column_lineage_list(
    trace: ColumnLineageTrace,
    *,
    use_color: bool = True,
) -> str:
    """Format column lineage as a flat dependency list."""

    style: CliStyle = CliStyle(use_color=use_color)
    if not trace.trace:
        return f"Column dependencies\n\n{_format_column(trace.target, style=style)}"
    displayed_trace: tuple[ColumnLineageEdge, ...] = trace.trace[:_HUMAN_COLUMN_TRACE_LIMIT]
    left_width: int = max(len(_column_id(edge.source)) for edge in displayed_trace)
    right_width: int = max(len(_column_id(edge.target)) for edge in displayed_trace)
    lines: list[str] = [style.object_name("Column dependencies"), ""]
    lines.extend(
        f"{_format_column(edge.source, style=style)}"
        f"{' ' * (left_width - len(_column_id(edge.source)))} "
        f"{style.muted('->')} "
        f"{_format_column(edge.target, style=style)}"
        f"{' ' * (right_width - len(_column_id(edge.target)))} "
        f"{_format_transform(edge, style=style)}"
        for edge in displayed_trace
    )
    lines.extend(_format_column_trace_limit_note(trace, style=style))
    return "\n".join(lines)


def format_lineage_tree(graph: LineageGraph, *, use_color: bool = True) -> str:
    """Format lineage graph for humans."""

    if len(graph.focus_keys) != 1 or graph.direction is None:
        return _format_graph_summary(graph, use_color=use_color)
    style: CliStyle = CliStyle(use_color=use_color)
    focus: CompiledObjectKey = graph.focus_keys[0]
    node_by_key: dict[CompiledObjectKey, LineageNode] = {node.key: node for node in graph.nodes}
    title: str = style.object_name("Lineage")
    direction: str = style.muted(graph.direction)
    lines: list[str] = [f"{title}  {_format_node(node_by_key[focus], style=style)}  {direction}"]
    if graph.direction in {"upstream", "both"}:
        upstream: dict[CompiledObjectKey, list[CompiledObjectKey]] = {}
        for parent, child in graph.edges:
            upstream.setdefault(child, []).append(parent)
        if graph.direction == "both":
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
    if graph.direction in {"downstream", "both"}:
        downstream: dict[CompiledObjectKey, list[CompiledObjectKey]] = {}
        for parent, child in graph.edges:
            downstream.setdefault(parent, []).append(child)
        if graph.direction == "both":
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


def format_column_lineage_tree(
    trace: ColumnLineageTrace,
    *,
    use_color: bool = True,
) -> str:
    """Format column lineage for humans without graph implementation terms."""

    style: CliStyle = CliStyle(use_color=use_color)
    title: str = style.object_name("Column trace")
    direction: str = style.muted(trace.direction)
    lines: list[str] = [
        f"{title}  {_format_column(trace.target, style=style)}  {direction}",
        "",
    ]
    if not trace.trace:
        lines.append(style.muted("  No column dependencies found"))
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
                style=style,
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
                style=style,
            )
        )
    lines.extend(_format_column_trace_limit_note(trace, style=style))
    return "\n".join(lines)


def _format_column_trace_branch(
    column: QualifiedLineageColumn,
    deps: dict[str, list[ColumnLineageEdge]],
    *,
    direction: str,
    prefix: str,
    seen: set[str],
    style: CliStyle,
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
        suffix: str = style.muted(" (already shown)") if related_id in seen else ""
        lines.append(
            f"{prefix}  {style.muted(arrow)} "
            f"{_format_column(related_column, style=style)} "
            f"{style.muted(f'({_human_transform_label(edge)})')}{suffix}"
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
                style=style,
            )
        )
    return lines


def _format_graph_summary(graph: LineageGraph, *, use_color: bool) -> str:
    style: CliStyle = CliStyle(use_color=use_color)
    title: str = style.object_name("Lineage graph")
    counts: str = style.muted(f"({len(graph.nodes)} nodes, {len(graph.edges)} edges)")
    lines: list[str] = [f"{title}  {counts}"]
    if graph.edges:
        lines.extend(
            f"{style.muted('  - ')}"
            f"{_format_key(parent, style=style)} "
            f"{style.muted('->')} "
            f"{_format_key(child, style=style)}"
            for parent, child in graph.edges
        )
    else:
        lines.extend(f"  {_format_node(node, style=style)}" for node in graph.nodes)
    return "\n".join(lines)


def _format_branch(
    key: CompiledObjectKey,
    deps: dict[CompiledObjectKey, list[CompiledObjectKey]],
    node_by_key: dict[CompiledObjectKey, LineageNode],
    *,
    prefix: str,
    seen: set[CompiledObjectKey],
    style: CliStyle,
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
        suffix: str = style.muted(" (already shown)") if child in seen else ""
        lines.append(
            f"{style.muted(prefix + branch)}{_format_node(node_by_key[child], style=style)}{suffix}"
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
                style=style,
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
    style: CliStyle,
) -> list[str]:
    if len(trace.trace) <= _HUMAN_COLUMN_TRACE_LIMIT:
        return []
    return [
        "",
        style.muted(f"Showing {_HUMAN_COLUMN_TRACE_LIMIT} of {len(trace.trace)} columns."),
        style.muted("Use --depth 1 to show direct column dependencies only."),
        style.muted("Use --format json for the full trace."),
    ]


def _format_transform(edge: ColumnLineageEdge, *, style: CliStyle) -> str:
    return style.muted(_human_transform_label(edge))


def _human_transform_label(edge: ColumnLineageEdge) -> str:
    if str(edge.transform_kind) == "star":
        return "from SELECT *"
    return str(edge.transform_kind)


def _format_node(node: LineageNode, *, style: CliStyle) -> str:
    parts: list[str] = [
        style.muted(str(node.key.resource_type)),
        style.section(node.key.name),
    ]
    if node.relative_path is not None:
        parts.append(style.muted(node.relative_path))
    return "  ".join(parts)


def _format_key(key: CompiledObjectKey, *, style: CliStyle) -> str:
    return f"{style.muted(str(key.resource_type))}:{style.section(key.name)}"


def _format_column(column: QualifiedLineageColumn, *, style: CliStyle) -> str:
    return style.section(_column_id(column))


def _column_id(column: QualifiedLineageColumn) -> str:
    return f"{column.resource_name}.{column.column_name}"


def _node_id(key: CompiledObjectKey) -> str:
    return f"{key.resource_type}:{key.name}"
