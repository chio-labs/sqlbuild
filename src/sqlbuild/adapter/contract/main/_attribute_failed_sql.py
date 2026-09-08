"""Exact failed-SQL attribution without changing mutable driver exception types."""

from __future__ import annotations

from sqlbuild.adapter.contract.exceptions import SqlStatementExecutionError


def attribute_failed_sql(*, error: Exception, sql: str) -> Exception:
    """Attach exact failed SQL without changing the driver's exception type when possible."""

    try:
        vars(error)["failed_sql"] = sql
    except (AttributeError, TypeError):
        return SqlStatementExecutionError(sql=sql, error=error)
    return error
