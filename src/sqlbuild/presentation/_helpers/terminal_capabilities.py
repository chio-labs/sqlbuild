"""Terminal capability implementations."""

from __future__ import annotations

import shutil

_DEFAULT_TERMINAL_COLUMNS: int = 120


def terminal_columns() -> int:
    """Return the current terminal width in columns."""

    return shutil.get_terminal_size(fallback=(_DEFAULT_TERMINAL_COLUMNS, 24)).columns
