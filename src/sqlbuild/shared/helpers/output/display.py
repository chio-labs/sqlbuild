"""Shared human-output display options."""

from __future__ import annotations

from collections.abc import Sequence

from sqlbuild.shared.models import DisplayOptions


def visible_entries[T](entries: Sequence[T], *, options: DisplayOptions) -> Sequence[T]:
    """Return entries visible under the current display cap."""

    if options.max_entries_per_section is None:
        return entries
    return entries[: options.max_entries_per_section]


def append_overflow_line(
    lines: list[str], *, total_count: int, visible_count: int, indent: str, options: DisplayOptions
) -> None:
    """Append a standard overflow hint when a section is truncated."""

    hidden_count: int = total_count - visible_count
    if hidden_count <= 0:
        return
    lines.append(f"{indent}... and {hidden_count} more (use {options.overflow_flag} to show all)")
