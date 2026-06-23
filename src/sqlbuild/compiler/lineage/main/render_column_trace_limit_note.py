"""Public entry for rendering the column-trace truncation note."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.compiler.lineage.helpers.tree_render import (
    render_column_trace_limit_note as _render_column_trace_limit_note,
)


def render_column_trace_limit_note(
    *,
    total: int,
    limit: int,
    note_style: Callable[[str], str],
) -> list[str]:
    """Render the shared column-trace truncation note when the trace is limited."""

    return _render_column_trace_limit_note(total=total, limit=limit, note_style=note_style)
