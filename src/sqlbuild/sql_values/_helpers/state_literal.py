"""Implementation helpers for typed warehouse-state SQL literals."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from sqlbuild.sql_values.exceptions import SqlValueRenderingError
from sqlbuild.sql_values.types import StateSqlValueType


def render_state_sql_literal(*, value: object | None, declared_type: StateSqlValueType) -> str:
    """Render a Python value according to its declared state-column type."""

    if value is None:
        return _typed_null(declared_type=declared_type)
    match declared_type:
        case StateSqlValueType.STRING:
            if not isinstance(value, str):
                raise SqlValueRenderingError("state string columns require str values")
            return _quoted(value=value)
        case StateSqlValueType.INTEGER:
            if isinstance(value, bool) or not isinstance(value, int):
                raise SqlValueRenderingError("state integer columns require int values")
            return f"CAST({value} AS BIGINT)"
        case StateSqlValueType.BOOLEAN:
            if not isinstance(value, bool):
                raise SqlValueRenderingError("state boolean columns require bool values")
            return "TRUE" if value else "FALSE"
        case StateSqlValueType.TIMESTAMP:
            if not isinstance(value, datetime):
                raise SqlValueRenderingError("state timestamp columns require datetime values")
            normalized: datetime = (
                value.replace(tzinfo=UTC)
                if value.tzinfo is None or value.utcoffset() is None
                else value.astimezone(UTC)
            )
            return f"CAST({_quoted(value=normalized.isoformat())} AS TIMESTAMP)"
        case StateSqlValueType.DATE:
            if isinstance(value, datetime) or not isinstance(value, date):
                raise SqlValueRenderingError("state date columns require date values")
            return f"CAST({_quoted(value=value.isoformat())} AS DATE)"
        case StateSqlValueType.JSON:
            try:
                serialized: str = json.dumps(
                    value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
                )
            except (TypeError, ValueError) as exc:
                raise SqlValueRenderingError(
                    "state JSON columns require JSON-serializable values"
                ) from exc
            return _quoted(value=serialized)


def _quoted(*, value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _typed_null(*, declared_type: StateSqlValueType) -> str:
    match declared_type:
        case StateSqlValueType.INTEGER:
            return "CAST(NULL AS BIGINT)"
        case StateSqlValueType.TIMESTAMP:
            return "CAST(NULL AS TIMESTAMP)"
        case StateSqlValueType.DATE:
            return "CAST(NULL AS DATE)"
        case _:
            return "NULL"
