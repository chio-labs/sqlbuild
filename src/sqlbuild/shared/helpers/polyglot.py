"""Optional Polyglot SQL import helper."""

from __future__ import annotations

from functools import cache
from typing import Any


@cache
def import_polyglot_sql() -> Any | None:
    """Return the polyglot_sql module when installed."""

    try:
        import polyglot_sql
    except ImportError:
        return None
    return polyglot_sql
