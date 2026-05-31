"""Public executor entrypoint for Region 2 SQL-read Python tracking."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.executor.python_nodes.helpers.region_2_execution import Region2PythonExecutionTracker


def create_region_2_python_execution_tracker(
    *,
    python_graph: PythonNodeGraph,
    selected_python_names: frozenset[str],
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection: Any,
    run_id: str,
    environment: str | None,
    vars: dict[str, object],
    is_reload: bool,
    default_database: str | None = None,
    default_schema: str | None = None,
    start_cursor_ts: datetime | None = None,
    end_cursor_ts: datetime | None = None,
    start_cursor_int: int | None = None,
    end_cursor_int: int | None = None,
) -> Region2PythonExecutionTracker:
    """Create a Region 2 Python execution tracker."""

    return Region2PythonExecutionTracker(
        python_graph=python_graph,
        selected_python_names=selected_python_names,
        adapter=adapter,
        connection_config=connection_config,
        connection=connection,
        run_id=run_id,
        environment=environment,
        vars=vars,
        is_reload=is_reload,
        default_database=default_database,
        default_schema=default_schema,
        start_cursor_ts=start_cursor_ts,
        end_cursor_ts=end_cursor_ts,
        start_cursor_int=start_cursor_int,
        end_cursor_int=end_cursor_int,
    )
