"""Optional Polyglot import helpers."""

from __future__ import annotations

from importlib import import_module
from typing import Any


def import_polyglot() -> Any | None:
    """Return the Polyglot SQL module when installed, otherwise None."""

    try:
        return import_module("polyglot_sql")
    except ImportError:
        return None


def import_polyglot_sql() -> Any | None:
    """Return the Polyglot SQL module when installed, otherwise None."""

    return import_polyglot()


def is_polyglot_available() -> bool:
    """Return whether Polyglot SQL can be imported."""

    return import_polyglot() is not None
