"""Public dialect compatibility normalization for Polyglot analysis input."""

from __future__ import annotations

from sqlbuild.compiler.sql_analysis._helpers.polyglot_normalization import (
    normalize_sql_for_polyglot_impl,
)


def normalize_sql_for_polyglot(*, sql: str, dialect: str | None) -> str:
    """Return analysis-equivalent SQL for Polyglot's supported dialect surface."""

    return normalize_sql_for_polyglot_impl(sql=sql, dialect=dialect)
