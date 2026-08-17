"""Public terminal width entry."""

from __future__ import annotations

from sqlbuild.presentation._helpers.terminal_capabilities import (
    terminal_columns as _terminal_columns,
)


def terminal_columns() -> int:
    """Return the current terminal width in columns."""

    return _terminal_columns()
