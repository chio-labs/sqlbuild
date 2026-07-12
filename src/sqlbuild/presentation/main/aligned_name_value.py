"""Public aligned name-value formatting entry."""

from __future__ import annotations

from sqlbuild.presentation.helpers.alignment import (
    format_aligned_name_value as _format_aligned_name_value,
)


def format_aligned_name_value(
    *,
    plain_name: str,
    styled_name: str,
    value: str,
    name_column_width: int,
    prefix: str = "  ",
) -> str:
    """Format one aligned name/value row using a plain-text width basis."""

    return _format_aligned_name_value(
        plain_name=plain_name,
        styled_name=styled_name,
        value=value,
        name_column_width=name_column_width,
        prefix=prefix,
    )
