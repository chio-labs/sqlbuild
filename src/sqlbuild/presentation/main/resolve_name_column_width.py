"""Public aligned name-column width entry."""

from __future__ import annotations

from sqlbuild.presentation.helpers.alignment import (
    resolve_name_column_width as _resolve_name_column_width,
)


def resolve_name_column_width(*, names: list[str] | tuple[str, ...], min_width: int = 20) -> int:
    """Resolve a left-column width from the longest visible name."""

    return _resolve_name_column_width(names=names, min_width=min_width)
