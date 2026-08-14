"""Public cursor-bound display entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.output.inclusive_cursor_end import (
    cursor_bound_display as _cursor_bound_display,
)


def cursor_bound_display(*, value: str, cursor_type: str | None, cursor_grain: str | None) -> str:
    """Render a cursor bound for display, collapsing a whole-day midnight timestamp to a date."""

    return _cursor_bound_display(value=value, cursor_type=cursor_type, cursor_grain=cursor_grain)
