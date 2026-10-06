"""Public zero-width cursor window entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.resolve.cursor import (
    empty_cursor_window as _empty_cursor_window,
)
from sqlbuild.compiler.planner.models import CursorBounds


def empty_cursor_window(*, cursor_type: str | None, cursor_start: str | None) -> CursorBounds:
    """Return a zero-width cursor window, which selects no rows from any filtered input."""

    return _empty_cursor_window(cursor_type=cursor_type, cursor_start=cursor_start)
