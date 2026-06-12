"""Public executor entrypoint for Python check nodes."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredCheckFunction
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.python_nodes.helpers.python_checks import execute_python_check_nodes
from sqlbuild.executor.python_nodes.models import (
    PythonCheckExecutionResult,
    PythonNodeExecutionResult,
    PythonNodeRunState,
)
from sqlbuild.executor.python_nodes.types import PythonIdentityRecorder
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.shared.models import SqlResourceRef


def execute_python_checks(
    *,
    check_functions: tuple[DiscoveredCheckFunction, ...],
    python_graph: PythonNodeGraph,
    upstream_python_results: tuple[PythonNodeExecutionResult, ...],
    upstream_load_results: tuple[LoadExecutionResult, ...],
    upstream_load_results_by_loader_name: Mapping[str, LoadExecutionResult] | None = None,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection: Any,
    run_id: str,
    target: str | None,
    vars: dict[str, object],
    is_reload: bool,
    run_state: PythonNodeRunState,
    default_database: str | None = None,
    default_schema: str | None = None,
    relation_targets: dict[SqlResourceRef, str] | None = None,
    start_cursor_ts: datetime | None = None,
    end_cursor_ts: datetime | None = None,
    start_cursor_int: int | None = None,
    end_cursor_int: int | None = None,
    logger: logging.Logger | None = None,
    providers: ProviderContainer | None = None,
    identity_recorder: PythonIdentityRecorder | None = None,
    result_store: Any | None = None,
    persist_node_results: bool = True,
) -> tuple[PythonCheckExecutionResult, ...]:
    """Execute check nodes after their selected Python dependencies have completed."""

    return execute_python_check_nodes(
        check_functions=check_functions,
        python_graph=python_graph,
        upstream_python_results=upstream_python_results,
        upstream_load_results=upstream_load_results,
        upstream_load_results_by_loader_name=upstream_load_results_by_loader_name,
        adapter=adapter,
        connection_config=connection_config,
        connection=connection,
        run_id=run_id,
        target=target,
        vars=vars,
        is_reload=is_reload,
        run_state=run_state,
        default_database=default_database,
        default_schema=default_schema,
        relation_targets=relation_targets,
        start_cursor_ts=start_cursor_ts,
        end_cursor_ts=end_cursor_ts,
        start_cursor_int=start_cursor_int,
        end_cursor_int=end_cursor_int,
        logger=logger,
        providers=providers,
        identity_recorder=identity_recorder,
        result_store=result_store,
        persist_node_results=persist_node_results,
    )
