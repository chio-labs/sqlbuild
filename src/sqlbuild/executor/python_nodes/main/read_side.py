"""Public executor entrypoint for Python read-side SQL-read Python tracking."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.executor.python_nodes.helpers.read_side_execution import (
    ReadSidePythonExecutionTracker,
)
from sqlbuild.shared.models import SqlResourceRef


def create_read_side_python_execution_tracker(
    *,
    python_graph: PythonNodeGraph,
    selected_python_names: frozenset[str],
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection: Any,
    run_id: str,
    target: str | None,
    vars: dict[str, object],
    is_reload: bool,
    default_database: str | None = None,
    default_schema: str | None = None,
    relation_targets: dict[SqlResourceRef, str] | None = None,
    start_cursor_ts: datetime | None = None,
    end_cursor_ts: datetime | None = None,
    start_cursor_int: int | None = None,
    end_cursor_int: int | None = None,
) -> ReadSidePythonExecutionTracker:
    """Create a read-side Python execution tracker."""

    return ReadSidePythonExecutionTracker(
        python_graph=python_graph,
        selected_python_names=selected_python_names,
        adapter=adapter,
        connection_config=connection_config,
        connection=connection,
        run_id=run_id,
        target=target,
        vars=vars,
        is_reload=is_reload,
        default_database=default_database,
        default_schema=default_schema,
        relation_targets=relation_targets,
        start_cursor_ts=start_cursor_ts,
        end_cursor_ts=end_cursor_ts,
        start_cursor_int=start_cursor_int,
        end_cursor_int=end_cursor_int,
    )
