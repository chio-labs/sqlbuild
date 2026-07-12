"""Public optional Polyglot import entry."""

from typing import Any

from sqlbuild.compiler.sql_analysis.helpers.polyglot import (
    import_polyglot as _import_polyglot,
)


def import_polyglot() -> Any | None:
    """Return the Polyglot SQL module when installed, otherwise None."""

    return _import_polyglot()
