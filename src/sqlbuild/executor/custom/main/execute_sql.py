"""Recorded SQL execution for custom materialization contexts."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder


def execute_sql_with_recording(
    *,
    adapter: BaseAdapter,
    connection: Any,
    sql: str,
    statement_recorder: StatementRecorder,
) -> Any:
    """Record a SQL statement before executing it through the adapter."""

    statement_recorder.record(sql)
    return adapter.execute(connection=connection, sql=sql)
