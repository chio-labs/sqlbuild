"""Public bounded-output overflow entry."""

from __future__ import annotations

from sqlbuild.presentation._helpers.display import append_overflow_line as _append_overflow_line
from sqlbuild.presentation.models import DisplayOptions


def append_overflow_line(
    *, lines: list[str], total_count: int, visible_count: int, indent: str, options: DisplayOptions
) -> list[str]:
    """Append a standard overflow hint when a section is truncated."""

    return _append_overflow_line(
        lines=lines,
        total_count=total_count,
        visible_count=visible_count,
        indent=indent,
        options=options,
    )
