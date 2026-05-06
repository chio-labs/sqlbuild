"""SQLGlot helpers for column lineage extraction."""

from __future__ import annotations

from importlib import import_module
from typing import Any

from sqlbuild.shared.helpers.sqlglot import import_sqlglot


def import_sqlglot_lineage() -> Any | None:
    """Return the sqlglot.lineage module when available."""

    if import_sqlglot() is None:
        return None
    try:
        return import_module("sqlglot.lineage")
    except ImportError:
        return None


def import_sqlglot_optimizer() -> Any | None:
    """Return SQLGlot optimizer helpers when available."""

    if import_sqlglot() is None:
        return None
    try:
        qualify_module: Any = import_module("sqlglot.optimizer.qualify")
        build_scope_module: Any = import_module("sqlglot.optimizer.scope")
    except ImportError:
        return None
    return {
        "qualify": qualify_module.qualify,
        "build_scope": build_scope_module.build_scope,
    }
