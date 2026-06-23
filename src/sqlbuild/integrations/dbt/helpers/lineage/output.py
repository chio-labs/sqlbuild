"""Mixed dbt/SQLBuild lineage output formatting."""

from __future__ import annotations

import json

from sqlbuild.compiler.lineage.main.render_column_trace_limit_note import (
    render_column_trace_limit_note,
)
from sqlbuild.compiler.lineage.main.render_column_trace_tree import render_column_trace_tree
from sqlbuild.compiler.lineage.main.render_dependency_tree import render_dependency_tree
from sqlbuild.compiler.lineage.main.serialize_column import serialize_column
from sqlbuild.compiler.lineage.main.serialize_column_edge import serialize_column_edge
from sqlbuild.compiler.lineage.models import ColumnLineageEdge, QualifiedLineageColumn
from sqlbuild.integrations.dbt.models import (
    DbtColumnLineageTrace,
    DbtCombinedGraphKey,
    DbtLineageGraph,
    DbtLineageNode,
)
from sqlbuild.integrations.dbt.types import DbtCombinedGraphOwner, DbtLineageDirection
from sqlbuild.shared.helpers.cli_style import CliStyle

_HUMAN_COLUMN_TRACE_LIMIT: int = 25


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


def format_dbt_column_lineage_json(trace: DbtColumnLineageTrace) -> str:
    """Serialize mixed dbt/SQLBuild column lineage as stable JSON."""

    payload: dict[str, object] = {
        "target": serialize_column(trace.target, render_resource_type=_render_resource_type),
        "direction": trace.direction.value,
        "metadata": {
            "max_depth": trace.max_depth,
            "analyzed_models": trace.analyzed_model_count,
            "truncated": trace.truncated,
            "warnings": list(trace.warnings),
        },
        "trace": [
            serialize_column_edge(edge, render_resource_type=_render_resource_type)
            for edge in trace.trace
        ],
    }
    return json.dumps(payload, indent=2)


def format_dbt_column_lineage_list(
    trace: DbtColumnLineageTrace,
    *,
    use_color: bool = True,
) -> str:
    """Format mixed dbt/SQLBuild column lineage as an edge list."""

    style: CliStyle = CliStyle(use_color=use_color)
    if not trace.trace:
        lines: list[str] = [
            style.object_name("Column dependencies"),
            "",
            _format_column(trace.target, style=style),
        ]
        lines.extend(_format_warnings(trace.warnings, style=style))
        return "\n".join(lines)
    displayed_trace: tuple[ColumnLineageEdge, ...] = trace.trace[:_HUMAN_COLUMN_TRACE_LIMIT]
    left_width: int = max(len(_column_id(edge.source)) for edge in displayed_trace)
    right_width: int = max(len(_column_id(edge.target)) for edge in displayed_trace)
    lines = [style.object_name("Column dependencies"), ""]
    lines.extend(
        f"{_format_column(edge.source, style=style)}"
        f"{' ' * (left_width - len(_column_id(edge.source)))} "
        f"{style.muted('->')} "
        f"{_format_column(edge.target, style=style)}"
        f"{' ' * (right_width - len(_column_id(edge.target)))} "
        f"{style.muted(str(edge.transform_kind))}"
        for edge in displayed_trace
    )
    lines.extend(
        render_column_trace_limit_note(
            total=len(trace.trace),
            limit=_HUMAN_COLUMN_TRACE_LIMIT,
            note_style=style.muted,
        )
    )
    lines.extend(_format_warnings(trace.warnings, style=style))
    return "\n".join(lines)


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
            render_dependency_tree(
                focus=focus,
                deps=upstream,
                seen={focus},
                format_node=lambda key: _format_node(node_by_key[key], style=style),
                sort_key=lambda key: key.stable_id,
                branch_style=style.muted,
                already_shown=lambda: style.muted(" (already shown)"),
            )
        )
    if graph.direction in {DbtLineageDirection.DOWNSTREAM, DbtLineageDirection.BOTH}:
        downstream: dict[DbtCombinedGraphKey, list[DbtCombinedGraphKey]] = {}
        for parent, child in graph.edges:
            downstream.setdefault(parent, []).append(child)
        if graph.direction == DbtLineageDirection.BOTH:
            lines.append(style.object_name("downstream"))
        lines.extend(
            render_dependency_tree(
                focus=focus,
                deps=downstream,
                seen={focus},
                format_node=lambda key: _format_node(node_by_key[key], style=style),
                sort_key=lambda key: key.stable_id,
                branch_style=style.muted,
                already_shown=lambda: style.muted(" (already shown)"),
            )
        )
    return "\n".join(lines)


def format_dbt_column_lineage_tree(
    trace: DbtColumnLineageTrace,
    *,
    use_color: bool = True,
) -> str:
    """Format mixed dbt/SQLBuild column lineage for humans."""

    style: CliStyle = CliStyle(use_color=use_color)
    lines: list[str] = [
        f"{style.object_name('Column trace')}  {_format_column_short(trace.target, style=style)}  "
        f"{style.muted(trace.direction.value)}",
        "",
    ]
    if not trace.trace:
        lines.append(style.muted("  No column dependencies found"))
        lines.extend(_format_warnings(trace.warnings, style=style))
        return "\n".join(lines)
    is_downstream: bool = trace.direction == DbtLineageDirection.DOWNSTREAM
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
                edge, is_downstream=is_downstream, style=style
            ),
            branch_style=style.muted,
            already_shown=lambda: style.muted(" (already shown)"),
            note_style=style.muted,
        )
    )
    lines.extend(_format_warnings(trace.warnings, style=style))
    return "\n".join(lines)


def _format_related_column(edge: ColumnLineageEdge, *, is_downstream: bool, style: CliStyle) -> str:
    related_column: QualifiedLineageColumn = edge.target if is_downstream else edge.source
    return (
        f"{_format_column_short(related_column, style=style)} "
        f"{style.muted(f'({edge.transform_kind})')}"
    )


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


def _render_resource_type(column: QualifiedLineageColumn) -> str:
    return str(column.resource_type)


def _format_node(node: DbtLineageNode, *, style: CliStyle) -> str:
    if node.key.owner == DbtCombinedGraphOwner.DBT:
        name: str = style.dbt_object_name(node.label)
    else:
        name = style.object_name(node.label)
    return f"{name} {style.muted(f'[{node.key.owner.value}]')}"


def _format_column(column: QualifiedLineageColumn, *, style: CliStyle) -> str:
    return style.object_name(_column_id(column))


def _format_column_short(column: QualifiedLineageColumn, *, style: CliStyle) -> str:
    return style.object_name(f"{_short_resource_name(column.resource_name)}:{column.column_name}")


def _short_resource_name(resource_name: str) -> str:
    """Drop the dbt unique-id prefix (model.<package>.) for human display."""

    return resource_name.rsplit(".", 1)[-1]


def _column_id(column: QualifiedLineageColumn) -> str:
    return f"{column.resource_name}:{column.column_name}"


def _format_warnings(warnings: tuple[str, ...], *, style: CliStyle) -> list[str]:
    if not warnings:
        return []
    return [
        "",
        style.object_name("Warnings"),
        *(style.muted(f"  {warning}") for warning in warnings),
    ]


def _format_graph_summary(*, graph: DbtLineageGraph, use_color: bool) -> str:
    style: CliStyle = CliStyle(use_color=use_color)
    lines: list[str] = [style.object_name("Lineage graph")]
    if graph.nodes:
        lines.append("")
        lines.extend(_format_node(node, style=style) for node in graph.nodes)
    return "\n".join(lines)
