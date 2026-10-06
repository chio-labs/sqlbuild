"""Time travel retention for SQLBuild state tables created on Snowflake."""

from __future__ import annotations

from sqlbuild.adapters.snowflake.constants import (
    INVALID_PARAMETER_VALUE_ERRNO,
    STATE_TABLE_RETENTION_PARAMETER,
)

_INVALID_RETENTION_MARKER: str = f"for parameter '{STATE_TABLE_RETENTION_PARAMETER}'"


def render_state_table_retention_sql(*, create_sql: str, retention_days: int) -> str:
    """Append the time travel retention clause to one state-table CREATE statement."""

    return f"{create_sql} {STATE_TABLE_RETENTION_PARAMETER} = {retention_days}"


def is_invalid_retention_error(error: Exception) -> bool:
    """Return whether Snowflake rejected the value as ``001008 ... for parameter '<retention>'``."""

    return getattr(
        error, "errno", None
    ) == INVALID_PARAMETER_VALUE_ERRNO and _INVALID_RETENTION_MARKER in str(error)
