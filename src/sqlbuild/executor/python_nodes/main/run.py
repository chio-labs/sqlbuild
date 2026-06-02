"""Public executor entrypoint for task/asset Python nodes."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.executor.python_nodes.helpers.execution import execute_python_nodes
from sqlbuild.executor.python_nodes.models import PythonNodeExecutorResult
from sqlbuild.executor.python_nodes.types import ExecutablePythonNode


def run_python_nodes(
    *,
    nodes: tuple[ExecutablePythonNode, ...],
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection: Any,
    run_id: str,
    target: str | None,
    vars: dict[str, object],
    is_reload: bool,
    statement_recorder: StatementRecorder,
    default_database: str | None = None,
    default_schema: str | None = None,
    start_cursor_ts: datetime | None = None,
    end_cursor_ts: datetime | None = None,
    start_cursor_int: int | None = None,
    end_cursor_int: int | None = None,
) -> PythonNodeExecutorResult:
    """Execute task/asset Python nodes in dependency order."""

    return execute_python_nodes(
        nodes=nodes,
        adapter=adapter,
        connection_config=connection_config,
        connection=connection,
        run_id=run_id,
        target=target,
        vars=vars,
        is_reload=is_reload,
        statement_recorder=statement_recorder,
        default_database=default_database,
        default_schema=default_schema,
        start_cursor_ts=start_cursor_ts,
        end_cursor_ts=end_cursor_ts,
        start_cursor_int=start_cursor_int,
        end_cursor_int=end_cursor_int,
    )
