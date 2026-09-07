"""Required Polyglot import helpers."""

from __future__ import annotations

from typing import Any

import polyglot_sql


def import_polyglot() -> Any:
    """Return SQLBuild's required Polyglot SQL module."""

    return polyglot_sql


def import_polyglot_sql() -> Any:
    """Return SQLBuild's required Polyglot SQL module."""

    return import_polyglot()


def is_polyglot_available() -> bool:
    """Return true because Polyglot SQL is a required dependency."""

    return True
