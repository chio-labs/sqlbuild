"""Bounded human-output implementations."""

from __future__ import annotations

from collections.abc import Sequence

from sqlbuild.presentation.models import DisplayOptions


def visible_entries[T](*, entries: Sequence[T], options: DisplayOptions) -> Sequence[T]:
    if options.max_entries_per_section is None:
        return entries
    return entries[: options.max_entries_per_section]


def append_overflow_line(
    *, lines: list[str], total_count: int, visible_count: int, indent: str, options: DisplayOptions
) -> list[str]:
    hidden_count: int = total_count - visible_count
    if hidden_count <= 0:
        return lines
    lines.append(f"{indent}... and {hidden_count} more (use {options.overflow_flag} to show all)")
    return lines
