"""Public status summary footer formatting entry."""

from __future__ import annotations

from sqlbuild.presentation._helpers.summary_footer import (
    format_summary_footer as _format_summary_footer,
)


def format_summary_footer(
    *, counts: tuple[tuple[str, int], ...], use_color: bool, elapsed: str | None = None
) -> str:
    """Format summary counts with semantic colors."""

    return _format_summary_footer(counts=counts, use_color=use_color, elapsed=elapsed)
