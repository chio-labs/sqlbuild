"""Public required Polyglot SQL import entry."""

from typing import Any

from sqlbuild.compiler.sql_analysis._helpers.polyglot import (
    import_polyglot_sql as _import_polyglot_sql,
)


def import_polyglot_sql() -> Any:
    """Return SQLBuild's required Polyglot SQL module."""

    return _import_polyglot_sql()
