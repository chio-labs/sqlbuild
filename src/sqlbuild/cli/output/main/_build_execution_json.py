"""Public build execution JSON formatting entrypoint."""

from __future__ import annotations

from sqlbuild.cli.output._helpers.execution_result_document import (
    format_build_execution_json as _format_build_execution_json,
)
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.python_nodes.models import (
    PythonCheckExecutionResult,
    PythonNodeExecutionResult,
)


def format_build_execution_json(
    *,
    result: BuildExecutionResult,
    plan: PlanOutput,
    python_node_results: tuple[PythonNodeExecutionResult, ...] = (),
    python_check_results: tuple[PythonCheckExecutionResult, ...] = (),
    command: str = "build",
    run_id: str | None = None,
    cost: dict[str, object] | None = None,
) -> str:
    """Format build command execution results as JSON."""

    return _format_build_execution_json(
        result=result,
        plan=plan,
        python_node_results=python_node_results,
        python_check_results=python_check_results,
        command=command,
        run_id=run_id,
        cost=cost,
    )
