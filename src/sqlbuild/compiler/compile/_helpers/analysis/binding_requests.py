"""Native schema-validation requests for model SQL."""

from __future__ import annotations

from sqlbuild.compiler.sql_analysis.main._normalize_analysis import normalize_analysis_sql
from sqlbuild.compiler.sql_analysis.models import (
    SqlSchemaValidationRequest,
)


def get_complete_schema_binding_request(
    *,
    query_sql: str,
    placeholders: dict[str, str] | None,
    dialect: str | None,
    binding_schema: dict[str, dict[str, str]],
    known_functions: tuple[str, ...] = (),
    known_types: tuple[str, ...] = (),
    cleaned_sql: str | None = None,
) -> SqlSchemaValidationRequest:
    """Build one stable native schema-validation request."""

    if cleaned_sql is None:
        cleaned_sql = normalize_analysis_sql(
            sql=query_sql, dialect=dialect, placeholders=placeholders
        )
    return SqlSchemaValidationRequest(
        sql=cleaned_sql,
        dialect=dialect,
        schema=binding_schema,
        known_functions=known_functions,
        known_types=known_types,
    )
