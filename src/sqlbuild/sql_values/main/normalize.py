"""Public entry point for typed SQL value normalization."""

from typing import cast

import sqlbuild._native as _native
from sqlbuild.sql_values.models import SqlValue, SqlValueLimits


def normalize_sql_value(
    *,
    raw_value: object,
    context: str,
    explicit_type: str | None = None,
    limits: SqlValueLimits | None = None,
) -> SqlValue:
    """Validate and normalize one authored value with contextual diagnostics."""

    applied: SqlValueLimits = SqlValueLimits() if limits is None else limits
    return cast(
        SqlValue,
        _native.normalize_typed_sql_value(
            raw_value,
            (context, explicit_type),
            (applied.max_depth, applied.max_elements, applied.max_size),
        ),
    )
