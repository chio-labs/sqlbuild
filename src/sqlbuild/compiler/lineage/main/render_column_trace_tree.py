"""Public entry for rendering a box-drawing column-trace tree with limit note."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.compiler.lineage._helpers.tree_render import (
    render_column_trace_branch,
    render_column_trace_limit_note,
)


def render_column_trace_tree[Column, Edge](
    *,
    target: Column,
    deps: dict[str, list[Edge]],
    total: int,
    limit: int,
    column_id: Callable[[Column], str],
    related_column: Callable[[Edge], Column],
    format_related: Callable[[Edge], str],
    branch_style: Callable[[str], str],
    already_shown: Callable[[], str],
    note_style: Callable[[str], str],
) -> list[str]:
    """Render the box-drawing column-trace tree lines plus any truncation note."""

    lines: list[str] = render_column_trace_branch(
        column=target,
        deps=deps,
        prefix="",
        seen={column_id(target)},
        column_id=column_id,
        related_column=related_column,
        format_related=format_related,
        branch_style=branch_style,
        already_shown=already_shown,
    )
    lines.extend(render_column_trace_limit_note(total=total, limit=limit, note_style=note_style))
    return lines
