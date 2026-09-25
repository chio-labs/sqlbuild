"""Resolve the effective connection's quoted-identifier binding policy."""

from sqlbuild.compiler.sql_analysis._helpers.identifier_case import (
    ignores_quoted_case as _ignores_quoted_case,
)


def ignores_quoted_case(*, connection: dict[str, object], dialect: str | None) -> bool:
    """Return whether quoted identifiers use the dialect's insensitive binding mode."""
    return _ignores_quoted_case(connection=connection, dialect=dialect)
