"""Public terminal color capability entry."""

from __future__ import annotations

from sqlbuild.presentation.helpers.terminal_capabilities import supports_color as _supports_color


def supports_color() -> bool:
    """Return whether the active output terminal supports color."""

    return _supports_color()
