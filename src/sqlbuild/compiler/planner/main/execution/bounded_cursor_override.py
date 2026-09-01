"""Public bounded cursor override resolution entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.output.inclusive_cursor_end import (
    resolve_bounded_cursor_override as _resolve_bounded_cursor_override,
)
from sqlbuild.compiler.planner.models import CursorBounds


def resolve_bounded_cursor_override(
    *,
    start_cursor_override: str | None,
    end_cursor_override: str | None,
    cursor_type: str | None,
    cursor_grain: str | None,
) -> CursorBounds | None:
    """Resolve a fully bounded inclusive operator override to an executable interval."""

    return _resolve_bounded_cursor_override(
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        cursor_type=cursor_type,
        cursor_grain=cursor_grain,
    )
