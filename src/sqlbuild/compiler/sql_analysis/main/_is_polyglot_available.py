"""Public Polyglot availability entry."""

from sqlbuild.compiler.sql_analysis._helpers.polyglot import (
    is_polyglot_available as _is_polyglot_available,
)


def is_polyglot_available() -> bool:
    """Return whether Polyglot SQL can be imported."""

    return _is_polyglot_available()
