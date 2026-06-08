"""Shared optional SQLGlot import helpers."""

from __future__ import annotations

from importlib import import_module
from typing import Any


def import_sqlglot() -> Any | None:
    """Return the SQLGlot module when installed, otherwise None."""

    try:
        return import_module("sqlglot")
    except ImportError:
        return None


def import_sqlglot_expressions() -> Any | None:
    """Return the SQLGlot expressions module when installed, otherwise None."""

    try:
        return import_module("sqlglot.expressions")
    except ImportError:
        return None


def is_sqlglot_available() -> bool:
    """Return whether SQLGlot can be imported."""

    return import_sqlglot() is not None
