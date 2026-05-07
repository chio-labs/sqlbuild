"""Shared helpers for aligned CLI text columns."""

from __future__ import annotations


def resolve_name_column_width(names: list[str] | tuple[str, ...], *, min_width: int = 20) -> int:
    """Resolve a left-column width from the longest visible name."""

    if not names:
        return min_width
    return max(min_width, max(len(name) for name in names))


def format_aligned_name_value(
    *,
    plain_name: str,
    styled_name: str,
    value: str,
    name_column_width: int,
    prefix: str = "  ",
) -> str:
    """Format one aligned name/value row using a plain-text width basis."""

    padding: str = " " * max(0, name_column_width - len(plain_name))
    return f"{prefix}{styled_name}{padding} {value}"
