"""Public executor entrypoint for one ready task/asset Python node."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.executor.python_nodes.helpers.execution import execute_ready_python_node
from sqlbuild.executor.python_nodes.models import PythonNodeExecutionResult, PythonNodeRunState
from sqlbuild.executor.python_nodes.types import ExecutablePythonNode
from sqlbuild.shared.models import SqlResourceRef


def run_ready_python_node(
    *,
    node: ExecutablePythonNode,
    upstream_results: tuple[PythonNodeExecutionResult, ...],
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection: Any,
    run_id: str,
    target: str | None,
    vars: dict[str, object],
    is_reload: bool,
    statement_recorder: StatementRecorder,
    run_state: PythonNodeRunState,
    default_database: str | None = None,
    default_schema: str | None = None,
    relation_targets: dict[SqlResourceRef, str] | None = None,
    start_cursor_ts: datetime | None = None,
    end_cursor_ts: datetime | None = None,
    start_cursor_int: int | None = None,
    end_cursor_int: int | None = None,
) -> PythonNodeExecutionResult:
    """Execute one scheduler-ready task/asset Python node."""

    return execute_ready_python_node(
        node=node,
        upstream_results=upstream_results,
        adapter=adapter,
        connection_config=connection_config,
        connection=connection,
        run_id=run_id,
        target=target,
        vars=vars,
        is_reload=is_reload,
        statement_recorder=statement_recorder,
        run_state=run_state,
        default_database=default_database,
        default_schema=default_schema,
        relation_targets=relation_targets,
        start_cursor_ts=start_cursor_ts,
        end_cursor_ts=end_cursor_ts,
        start_cursor_int=start_cursor_int,
        end_cursor_int=end_cursor_int,
    )
