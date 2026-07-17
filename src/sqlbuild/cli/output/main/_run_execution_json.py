"""Public run execution JSON formatting entrypoint."""

from __future__ import annotations

from sqlbuild.cli.output._helpers.execution_protocol_v1 import (
    format_run_execution_json as _format_run_execution_json,
)
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.python_nodes.models import PythonNodeExecutionResult


def format_run_execution_json(
    *,
    result: BuildExecutionResult,
    plan: PlanOutput,
    python_node_results: tuple[PythonNodeExecutionResult, ...] = (),
) -> str:
    """Format run command execution results as JSON."""

    return _format_run_execution_json(
        result=result, plan=plan, python_node_results=python_node_results
    )
