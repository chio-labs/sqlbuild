"""Generic box-drawing tree renderers shared by lineage output commands.

This module is intentionally dependency-neutral: it operates on opaque node and
column values through caller-provided callables, so both native and dbt lineage
output can share one rendering implementation and never drift in style.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from _typeshed import SupportsRichComparison as SupportsSortKey
else:
    SupportsSortKey = object

_BRANCH_LAST: str = "└── "
_BRANCH_MID: str = "├── "
_CONTINUATION_LAST: str = "    "
_CONTINUATION_MID: str = "│   "


def render_dependency_branch[Node: Hashable](
    node: Node,
    deps: dict[Node, list[Node]],
    *,
    prefix: str,
    seen: set[Node],
    format_node: Callable[[Node], str],
    sort_key: Callable[[Node], SupportsSortKey],
    branch_style: Callable[[str], str],
    already_shown: Callable[[], str],
) -> list[str]:
    """Render a box-drawing dependency branch for opaque node values."""

    lines: list[str] = []
    children: list[Node] = sorted(deps.get(node, ()), key=sort_key)
    index: int
    child: Node
    for index, child in enumerate(children):
        is_last: bool = index == len(children) - 1
        branch: str = _BRANCH_LAST if is_last else _BRANCH_MID
        continuation: str = _CONTINUATION_LAST if is_last else _CONTINUATION_MID
        suffix: str = already_shown() if child in seen else ""
        lines.append(f"{branch_style(prefix + branch)}{format_node(child)}{suffix}")
        if child in seen:
            continue
        lines.extend(
            render_dependency_branch(
                child,
                deps,
                prefix=prefix + continuation,
                seen=seen | {child},
                format_node=format_node,
                sort_key=sort_key,
                branch_style=branch_style,
                already_shown=already_shown,
            )
        )
    return lines


def render_column_trace_branch[Column, Edge](
    column: Column,
    deps: dict[str, list[Edge]],
    *,
    prefix: str,
    seen: set[str],
    column_id: Callable[[Column], str],
    related_column: Callable[[Edge], Column],
    format_related: Callable[[Edge], str],
    branch_style: Callable[[str], str],
    already_shown: Callable[[], str],
) -> list[str]:
    """Render a box-drawing column-trace branch for opaque column/edge values."""

    lines: list[str] = []
    edges: list[Edge] = sorted(
        deps.get(column_id(column), ()),
        key=lambda edge: column_id(related_column(edge)),
    )
    index: int
    edge: Edge
    for index, edge in enumerate(edges):
        is_last: bool = index == len(edges) - 1
        branch: str = _BRANCH_LAST if is_last else _BRANCH_MID
        continuation: str = _CONTINUATION_LAST if is_last else _CONTINUATION_MID
        related: Column = related_column(edge)
        related_id: str = column_id(related)
        suffix: str = already_shown() if related_id in seen else ""
        lines.append(f"{prefix}{branch_style(branch)}{format_related(edge)}{suffix}")
        if related_id in seen:
            continue
        lines.extend(
            render_column_trace_branch(
                related,
                deps,
                prefix=prefix + continuation,
                seen=seen | {related_id},
                column_id=column_id,
                related_column=related_column,
                format_related=format_related,
                branch_style=branch_style,
                already_shown=already_shown,
            )
        )
    return lines


def render_column_trace_limit_note(
    *,
    total: int,
    limit: int,
    note_style: Callable[[str], str],
) -> list[str]:
    """Render the shared truncation note when a column trace is limited."""

    if total <= limit:
        return []
    return [
        "",
        note_style(f"Showing {limit} of {total} columns."),
        note_style("Use --depth 1 to show direct column dependencies only."),
        note_style("Use --format json for the full trace."),
    ]
