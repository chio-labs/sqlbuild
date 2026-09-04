"""Public inclusive cursor end-bound formatting entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.output.inclusive_cursor_end import (
    advance_discovered_cursor_end as _advance_discovered_end,
)
from sqlbuild.compiler.planner._helpers.output.inclusive_cursor_end import (
    inclusive_cursor_end as _inclusive_cursor_end,
)


def inclusive_cursor_end(*, end: str, cursor_type: str | None, cursor_grain: str | None) -> str:
    """Return the last cursor value included by an exclusive end bound."""

    return _inclusive_cursor_end(end=end, cursor_type=cursor_type, cursor_grain=cursor_grain)


def _advance_discovered_cursor_end(
    *, value: object, cursor_type: str | None, cursor_grain: str | None
) -> object:
    """Forward observed maxima to the shared canonical partition helper."""

    return _advance_discovered_end(value=value, cursor_type=cursor_type, cursor_grain=cursor_grain)
