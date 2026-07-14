"""Aligned CLI text implementations."""

from __future__ import annotations


def resolve_name_column_width(*, names: list[str] | tuple[str, ...], min_width: int = 20) -> int:
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
    padding: str = " " * max(0, name_column_width - len(plain_name))
    return f"{prefix}{styled_name}{padding} {value}"
