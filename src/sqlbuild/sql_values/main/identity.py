"""Public entry point for typed SQL value identity."""

from sqlbuild.sql_values._helpers.normalization import sql_value_identity as _sql_value_identity
from sqlbuild.sql_values.models import SqlValue


def sql_value_identity(*, value: SqlValue) -> tuple[object, ...]:
    """Return the normalized typed identity of a SQL value."""

    return _sql_value_identity(value=value)
