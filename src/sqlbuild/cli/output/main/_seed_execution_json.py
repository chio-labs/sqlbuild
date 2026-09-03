"""Public seed execution JSON formatting entrypoint."""

from __future__ import annotations

from sqlbuild.cli.output._helpers.execution_result_document import (
    format_seed_execution_json as _format_seed_execution_json,
)
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.build.models import SeedExecutionResult


def format_seed_execution_json(
    *, results: tuple[SeedExecutionResult, ...], plan: PlanOutput
) -> str:
    """Format seed command execution results as JSON."""

    return _format_seed_execution_json(results=results, plan=plan)
