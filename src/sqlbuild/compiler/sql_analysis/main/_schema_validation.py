"""Public schema-aware SQL validation query."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.sql_analysis._helpers.schema_validation import (
    get_schema_validation as _get_schema_validation,
)
from sqlbuild.compiler.sql_analysis.models import SqlBindingResult


def get_schema_validation(
    *, sql: str, dialect: str | None, schema: Mapping[str, Mapping[str, str]]
) -> SqlBindingResult:
    """Return stable SQLBuild binding diagnostics for one complete schema."""

    return _get_schema_validation(sql=sql, dialect=dialect, schema=schema)
