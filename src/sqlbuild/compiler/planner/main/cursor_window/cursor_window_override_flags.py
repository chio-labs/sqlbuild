"""Public naming of the CLI flags that set a cursor window explicitly."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.resolve.cursor import (
    cursor_window_override_flags as _cursor_window_override_flags,
)


def cursor_window_override_flags(*, cursor_type: str | None) -> str:
    """Name the CLI flags that set a cursor window explicitly for this cursor type."""

    return _cursor_window_override_flags(cursor_type=cursor_type)
