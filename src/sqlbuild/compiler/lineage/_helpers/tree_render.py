"""Generic box-drawing tree renderers shared by lineage output commands."""

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
    *,
    node: Node,
    deps: dict[Node, list[Node]],
    prefix: str,
    seen: set[Node],
    format_node: Callable[[Node], str],
    sort_key: Callable[[Node], SupportsSortKey],
    branch_style: Callable[[str], str],
    already_shown: Callable[[], str],
) -> list[str]:
    """Render a box-drawing dependency branch, expanding each node once across the tree."""

    lines: list[str] = []
    shown: set[Node] = set(seen)
    pending: list[tuple[Node, str, bool]] = _pending_children(
        children=sorted(deps.get(node, ()), key=sort_key), prefix=prefix
    )
    while pending:
        child: Node
        child_prefix: str
        is_last: bool
        child, child_prefix, is_last = pending.pop()
        branch: str = _BRANCH_LAST if is_last else _BRANCH_MID
        suffix: str = already_shown() if child in shown else ""
        lines.append(f"{branch_style(child_prefix + branch)}{format_node(child)}{suffix}")
        if child in shown:
            continue
        shown.add(child)
        continuation: str = _CONTINUATION_LAST if is_last else _CONTINUATION_MID
        pending.extend(
            _pending_children(
                children=sorted(deps.get(child, ()), key=sort_key),
                prefix=child_prefix + continuation,
            )
        )
    return lines


def render_column_trace_branch[Column, Edge](
    *,
    column: Column,
    deps: dict[str, list[Edge]],
    prefix: str,
    seen: set[str],
    column_id: Callable[[Column], str],
    related_column: Callable[[Edge], Column],
    format_related: Callable[[Edge], str],
    branch_style: Callable[[str], str],
    already_shown: Callable[[], str],
) -> list[str]:
    """Render a box-drawing column-trace branch, expanding each column once across the tree."""

    lines: list[str] = []
    shown: set[str] = set(seen)
    pending: list[tuple[Edge, str, bool]] = _pending_children(
        children=_sorted_edges(
            edges=deps.get(column_id(column), ()),
            column_id=column_id,
            related_column=related_column,
        ),
        prefix=prefix,
    )
    while pending:
        edge: Edge
        edge_prefix: str
        is_last: bool
        edge, edge_prefix, is_last = pending.pop()
        branch: str = _BRANCH_LAST if is_last else _BRANCH_MID
        related: Column = related_column(edge)
        related_id: str = column_id(related)
        suffix: str = already_shown() if related_id in shown else ""
        lines.append(f"{edge_prefix}{branch_style(branch)}{format_related(edge)}{suffix}")
        if related_id in shown:
            continue
        shown.add(related_id)
        continuation: str = _CONTINUATION_LAST if is_last else _CONTINUATION_MID
        pending.extend(
            _pending_children(
                children=_sorted_edges(
                    edges=deps.get(related_id, ()),
                    column_id=column_id,
                    related_column=related_column,
                ),
                prefix=edge_prefix + continuation,
            )
        )
    return lines


def _pending_children[Item](*, children: list[Item], prefix: str) -> list[tuple[Item, str, bool]]:
    last: int = len(children) - 1
    return [(child, prefix, index == last) for index, child in reversed(list(enumerate(children)))]


def _sorted_edges[Column, Edge](
    *,
    edges: list[Edge] | tuple[()],
    column_id: Callable[[Column], str],
    related_column: Callable[[Edge], Column],
) -> list[Edge]:
    return sorted(edges, key=lambda edge: column_id(related_column(edge)))


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
