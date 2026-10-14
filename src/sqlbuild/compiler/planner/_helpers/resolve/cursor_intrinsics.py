"""Render cursor intrinsics with one interval's adapter-typed bound literals."""

from __future__ import annotations

from sqlbuild._native import cursor_sentinel_to_token as sentinel_to_token
from sqlbuild._native import resolve_cursor_intrinsics
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import CursorBounds


def render_cursor_intrinsic_bounds(
    *, sql: str, bounds: CursorBounds, cursor_type: str | None, adapter: BaseAdapter
) -> str:
    """Replace `__cursor_start()` / `__cursor_end()` with the adapter's typed bound literals."""

    rendered, _ = resolve_cursor_intrinsics(
        sql=sql,
        start_sql=adapter.render_cursor_bound_literal(
            value=sentinel_to_token(sentinel=bounds.start), cursor_type=cursor_type
        ),
        end_sql=adapter.render_cursor_bound_literal(
            value=sentinel_to_token(sentinel=bounds.end), cursor_type=cursor_type
        ),
    )
    return rendered
