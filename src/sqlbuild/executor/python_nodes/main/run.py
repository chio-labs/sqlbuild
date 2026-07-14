"""Public executor entrypoint for task/asset Python nodes."""

from __future__ import annotations

from sqlbuild.adapter.classes.statement_recorder import StatementRecorder
from sqlbuild.executor.python_nodes._helpers.execution import execute_python_nodes
from sqlbuild.executor.python_nodes.models import PythonNodeExecutorResult, PythonNodeRuntime
from sqlbuild.executor.python_nodes.types import ExecutablePythonNode


def run_python_nodes(
    *,
    nodes: tuple[ExecutablePythonNode, ...],
    runtime: PythonNodeRuntime,
    statement_recorder: StatementRecorder,
) -> PythonNodeExecutorResult:
    """Execute task/asset Python nodes in dependency order."""

    return execute_python_nodes(
        nodes=nodes,
        runtime=runtime,
        statement_recorder=statement_recorder,
    )
