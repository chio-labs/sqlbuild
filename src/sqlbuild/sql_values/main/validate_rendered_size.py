"""Rendered typed SQL value size validation."""

from sqlbuild.sql_values.constants import DEFAULT_MAX_SQL_VALUE_SIZE
from sqlbuild.sql_values.exceptions import SqlValueValidationError


def validate_rendered_sql_value_size(
    *,
    rendered_sql: str,
    context: str,
    max_size: int = DEFAULT_MAX_SQL_VALUE_SIZE,
) -> None:
    """Reject adapter SQL that exceeds the shared UTF-8 byte limit."""

    rendered_size: int = len(rendered_sql.encode("utf-8"))
    if rendered_size > max_size:
        raise SqlValueValidationError(
            f"{context} rendered value is {rendered_size} bytes; maximum is {max_size} bytes"
        )
