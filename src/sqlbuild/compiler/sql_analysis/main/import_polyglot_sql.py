"""Public optional Polyglot SQL import entry."""

from typing import Any

from sqlbuild.compiler.sql_analysis._helpers.polyglot import (
    import_polyglot_sql as _import_polyglot_sql,
)


def import_polyglot_sql() -> Any | None:
    """Return the Polyglot SQL module when installed, otherwise None."""

    return _import_polyglot_sql()
