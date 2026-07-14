"""Lineage output formatting."""

from __future__ import annotations

import json

from sqlbuild.cli.commands.helpers.lineage.constants import (
    BOTH_DIRECTIONS,
    DOWNSTREAM_DIRECTION,
    UPSTREAM_DIRECTION,
)
from sqlbuild.cli.commands.helpers.lineage.models import (
    ColumnLineageTrace,
    LineageGraph,
    LineageNode,
)
from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.main.render_column_trace_limit_note import (
    render_column_trace_limit_note,
)
from sqlbuild.compiler.lineage.main.render_column_trace_tree import render_column_trace_tree
from sqlbuild.compiler.lineage.main.render_dependency_tree import render_dependency_tree
from sqlbuild.compiler.lineage.main.serialize_column import serialize_column
from sqlbuild.compiler.lineage.main.serialize_column_edge import serialize_column_edge
from sqlbuild.compiler.lineage.models import ColumnLineageEdge, QualifiedLineageColumn
from sqlbuild.compiler.lineage.types import ColumnTransformKind
from sqlbuild.presentation.classes.cli_style import CliStyle

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
        "target": serialize_column(column=trace.target, render_resource_type=_render_resource_type),
        "direction": trace.direction,
        "metadata": {
            "mode": trace.mode.value,
            "max_depth": trace.max_depth,
            "analyzed_models": trace.analyzed_model_count,
            "truncated": trace.truncated,
        },
        "trace": [
            serialize_column_edge(edge=edge, render_resource_type=_render_resource_type)
            for edge in trace.trace
        ],
    }
    return json.dumps(payload, indent=2)


def format_lineage_list(*, graph: LineageGraph, use_color: bool = True) -> str:
    """Format lineage graph as an edge list."""

    style: CliStyle = CliStyle(use_color=use_color)
    if not graph.edges:
        return "\n".join(_format_key(key=node.key, style=style) for node in graph.nodes)
    left_width: int = max(len(_node_id(upstream)) for upstream, _downstream in graph.edges)
    return "\n".join(
        f"{_format_key(key=upstream, style=style)}"
        f"{' ' * (left_width - len(_node_id(upstream)))} "
        f"{style.muted('->')} "
        f"{_format_key(key=downstream, style=style)}"
        for upstream, downstream in graph.edges
    )


def format_column_lineage_list(
    *,
    trace: ColumnLineageTrace,
    use_color: bool = True,
) -> str:
    """Format column lineage as a flat dependency list."""

    style: CliStyle = CliStyle(use_color=use_color)
    if not trace.trace:
        return f"Column dependencies\n\n{_format_column(column=trace.target, style=style)}"
    displayed_trace: tuple[ColumnLineageEdge, ...] = trace.trace[:_HUMAN_COLUMN_TRACE_LIMIT]
    left_width: int = max(len(_column_id(edge.source)) for edge in displayed_trace)
    right_width: int = max(len(_column_id(edge.target)) for edge in displayed_trace)
    lines: list[str] = [style.object_name("Column dependencies"), ""]
    lines.extend(
        f"{_format_column(column=edge.source, style=style)}"
        f"{' ' * (left_width - len(_column_id(edge.source)))} "
        f"{style.muted('->')} "
        f"{_format_column(column=edge.target, style=style)}"
        f"{' ' * (right_width - len(_column_id(edge.target)))} "
        f"{_format_transform(edge=edge, style=style)}"
        for edge in displayed_trace
    )
    lines.extend(
        render_column_trace_limit_note(
            total=len(trace.trace),
            limit=_HUMAN_COLUMN_TRACE_LIMIT,
            note_style=style.muted,
        )
    )
    return "\n".join(lines)


def format_lineage_tree(*, graph: LineageGraph, use_color: bool = True) -> str:
    """Format lineage graph for humans."""

    if len(graph.focus_keys) != 1 or graph.direction is None:
        return _format_graph_summary(graph=graph, use_color=use_color)
    style: CliStyle = CliStyle(use_color=use_color)
    focus: CompiledObjectKey = graph.focus_keys[0]
    node_by_key: dict[CompiledObjectKey, LineageNode] = {node.key: node for node in graph.nodes}
    title: str = style.object_name("Lineage")
    direction: str = style.muted(graph.direction)
    lines: list[str] = [
        f"{title}  {_format_node(node=node_by_key[focus], style=style)}  {direction}"
    ]
    if graph.direction in {UPSTREAM_DIRECTION, BOTH_DIRECTIONS}:
        upstream: dict[CompiledObjectKey, list[CompiledObjectKey]] = {}
        for parent, child in graph.edges:
            upstream.setdefault(child, []).append(parent)
        if graph.direction == BOTH_DIRECTIONS:
            lines.append(style.object_name("upstream"))
        lines.extend(
            render_dependency_tree(
                focus=focus,
                deps=upstream,
                seen={focus},
                format_node=lambda key: _format_node(node=node_by_key[key], style=style),
                sort_key=lambda key: (str(key.resource_type), key.name),
                branch_style=style.muted,
                already_shown=lambda: style.muted(" (already shown)"),
            )
        )
    if graph.direction in {DOWNSTREAM_DIRECTION, BOTH_DIRECTIONS}:
        downstream: dict[CompiledObjectKey, list[CompiledObjectKey]] = {}
        for parent, child in graph.edges:
            downstream.setdefault(parent, []).append(child)
        if graph.direction == BOTH_DIRECTIONS:
            lines.append(style.object_name("downstream"))
        lines.extend(
            render_dependency_tree(
                focus=focus,
                deps=downstream,
                seen={focus},
                format_node=lambda key: _format_node(node=node_by_key[key], style=style),
                sort_key=lambda key: (str(key.resource_type), key.name),
                branch_style=style.muted,
                already_shown=lambda: style.muted(" (already shown)"),
            )
        )
    return "\n".join(lines)


def format_column_lineage_tree(
    *,
    trace: ColumnLineageTrace,
    use_color: bool = True,
) -> str:
    """Format column lineage for humans without graph implementation terms."""

    style: CliStyle = CliStyle(use_color=use_color)
    title: str = style.object_name("Column trace")
    direction: str = style.muted(trace.direction)
    lines: list[str] = [
        f"{title}  {_format_column(column=trace.target, style=style)}  {direction}",
        "",
    ]
    if not trace.trace:
        lines.append(style.muted("  No column dependencies found"))
        return "\n".join(lines)
    is_downstream: bool = trace.direction == DOWNSTREAM_DIRECTION
    deps: dict[str, list[ColumnLineageEdge]] = {}
    for edge in trace.trace[:_HUMAN_COLUMN_TRACE_LIMIT]:
        key_column: QualifiedLineageColumn = edge.source if is_downstream else edge.target
        deps.setdefault(_column_id(key_column), []).append(edge)
    lines.extend(
        render_column_trace_tree(
            target=trace.target,
            deps=deps,
            total=len(trace.trace),
            limit=_HUMAN_COLUMN_TRACE_LIMIT,
            column_id=_column_id,
            related_column=lambda edge: edge.target if is_downstream else edge.source,
            format_related=lambda edge: _format_related_column(
                edge=edge, is_downstream=is_downstream, style=style
            ),
            branch_style=style.muted,
            already_shown=lambda: style.muted(" (already shown)"),
            note_style=style.muted,
        )
    )
    return "\n".join(lines)


def _format_related_column(*, edge: ColumnLineageEdge, is_downstream: bool, style: CliStyle) -> str:
    related_column: QualifiedLineageColumn = edge.target if is_downstream else edge.source
    return (
        f"{_format_column(column=related_column, style=style)} "
        f"{style.muted(f'({_human_transform_label(edge)})')}"
    )


def _format_graph_summary(*, graph: LineageGraph, use_color: bool) -> str:
    style: CliStyle = CliStyle(use_color=use_color)
    title: str = style.object_name("Lineage graph")
    counts: str = style.muted(f"({len(graph.nodes)} nodes, {len(graph.edges)} edges)")
    lines: list[str] = [f"{title}  {counts}"]
    if graph.edges:
        lines.extend(
            f"{style.muted('  - ')}"
            f"{_format_key(key=parent, style=style)} "
            f"{style.muted('->')} "
            f"{_format_key(key=child, style=style)}"
            for parent, child in graph.edges
        )
    else:
        lines.extend(f"  {_format_node(node=node, style=style)}" for node in graph.nodes)
    return "\n".join(lines)


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


def _render_resource_type(column: QualifiedLineageColumn) -> str:
    return CompiledResourceType(column.resource_type).value


def _format_transform(*, edge: ColumnLineageEdge, style: CliStyle) -> str:
    return style.muted(_human_transform_label(edge))


def _human_transform_label(edge: ColumnLineageEdge) -> str:
    if str(edge.transform_kind) == ColumnTransformKind.STAR:
        return "from SELECT *"
    return str(edge.transform_kind)


def _format_node(*, node: LineageNode, style: CliStyle) -> str:
    parts: list[str] = [
        style.muted(str(node.key.resource_type)),
        style.section(node.key.name),
    ]
    if node.relative_path is not None:
        parts.append(style.muted(node.relative_path))
    return "  ".join(parts)


def _format_key(*, key: CompiledObjectKey, style: CliStyle) -> str:
    return f"{style.muted(str(key.resource_type))}:{style.section(key.name)}"


def _format_column(*, column: QualifiedLineageColumn, style: CliStyle) -> str:
    return style.section(_column_id(column))


def _column_id(column: QualifiedLineageColumn) -> str:
    return f"{column.resource_name}.{column.column_name}"


def _node_id(key: CompiledObjectKey) -> str:
    return f"{key.resource_type}:{key.name}"
