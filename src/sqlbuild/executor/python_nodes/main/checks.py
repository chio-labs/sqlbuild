"""Public executor entrypoint for Python check nodes."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.discovery.models import DiscoveredCheckFunction
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.python_nodes._helpers.python_checks import execute_python_check_nodes
from sqlbuild.executor.python_nodes.models import (
    PythonCheckCallbacks,
    PythonCheckExecutionResult,
    PythonNodeExecutionResult,
    PythonNodeRunState,
    PythonNodeRuntime,
)


def execute_python_checks(
    *,
    check_functions: tuple[DiscoveredCheckFunction, ...],
    python_graph: PythonNodeGraph,
    upstream_python_results: tuple[PythonNodeExecutionResult, ...],
    upstream_load_results: tuple[LoadExecutionResult, ...],
    runtime: PythonNodeRuntime,
    run_state: PythonNodeRunState,
    upstream_load_results_by_loader_name: Mapping[str, LoadExecutionResult] | None = None,
    callbacks: PythonCheckCallbacks | None = None,
    require_upstream_results: bool = True,
) -> tuple[PythonCheckExecutionResult, ...]:
    """Execute check nodes after their selected Python dependencies have completed."""

    return execute_python_check_nodes(
        check_functions=check_functions,
        python_graph=python_graph,
        upstream_python_results=upstream_python_results,
        upstream_load_results=upstream_load_results,
        runtime=runtime,
        run_state=run_state,
        upstream_load_results_by_loader_name=upstream_load_results_by_loader_name,
        callbacks=callbacks,
        require_upstream_results=require_upstream_results,
    )
