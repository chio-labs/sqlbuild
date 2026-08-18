"""Terminal capability implementations."""

from __future__ import annotations

import os
import shutil
import sys

_DEFAULT_TERMINAL_COLUMNS: int = 120


def supports_color() -> bool:
    if os.environ.get("NO_COLOR") is not None:
        return False
    if not hasattr(sys.stdout, "isatty"):
        return False
    return sys.stdout.isatty()


def terminal_columns() -> int:
    """Return the current terminal width in columns."""

    return shutil.get_terminal_size(fallback=(_DEFAULT_TERMINAL_COLUMNS, 24)).columns
