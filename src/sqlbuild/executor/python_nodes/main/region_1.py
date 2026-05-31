"""Public executor entrypoint for Region 1 Python/loader nodes."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.executor.python_nodes.helpers.region_1_execution import (
    execute_region_1_python_loader_nodes,
)
from sqlbuild.executor.python_nodes.models import Region1PythonLoaderExecutorResult
from sqlbuild.shared.types import ExecutionResourceKind
from sqlbuild.spec.models.source import SourceEntry


def run_region_1_python_loader_nodes(
    *,
    python_graph: PythonNodeGraph,
    selected_python_names: frozenset[str],
    loader_functions: tuple[DiscoveredLoaderFunction, ...],
    source_map: Mapping[str, SourceEntry],
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
    use_color: bool = False,
    on_node_start: Callable[[str, ExecutionResourceKind], None] | None = None,
    on_node_complete: Callable[[object], None] | None = None,
) -> Region1PythonLoaderExecutorResult:
    """Execute Region 1 task/asset/loader nodes in lifecycle order."""

    return execute_region_1_python_loader_nodes(
        python_graph=python_graph,
        selected_python_names=selected_python_names,
        loader_functions=loader_functions,
        source_map=source_map,
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
        use_color=use_color,
        on_node_start=on_node_start,
        on_node_complete=on_node_complete,
    )
