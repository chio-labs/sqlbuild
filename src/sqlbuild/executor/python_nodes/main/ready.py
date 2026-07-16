"""Public executor entrypoint for one ready task/asset Python node."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.executor.python_nodes._helpers.execution import execute_ready_python_node
from sqlbuild.executor.python_nodes.models import (
    PythonNodeExecutionResult,
    PythonNodeRunState,
    PythonNodeRuntime,
)
from sqlbuild.executor.python_nodes.types import ExecutablePythonNode


def run_ready_python_node(
    *,
    node: ExecutablePythonNode,
    upstream_results: tuple[PythonNodeExecutionResult, ...],
    runtime: PythonNodeRuntime,
    statement_recorder: StatementRecorder,
    run_state: PythonNodeRunState,
) -> PythonNodeExecutionResult:
    """Execute one scheduler-ready task/asset Python node."""

    return execute_ready_python_node(
        node=node,
        upstream_results=upstream_results,
        runtime=runtime,
        statement_recorder=statement_recorder,
        run_state=run_state,
    )
