"""Public entry point for typed SQL value normalization."""

from sqlbuild.sql_values._helpers.normalization import normalize_sql_value as _normalize_sql_value
from sqlbuild.sql_values.models import SqlValue, SqlValueLimits


def normalize_sql_value(
    *,
    raw_value: object,
    context: str,
    explicit_type: str | None = None,
    limits: SqlValueLimits | None = None,
) -> SqlValue:
    """Validate and normalize one authored value with contextual diagnostics."""

    if limits is None:
        return _normalize_sql_value(
            raw_value=raw_value, context=context, explicit_type=explicit_type
        )
    return _normalize_sql_value(
        raw_value=raw_value, context=context, explicit_type=explicit_type, limits=limits
    )
