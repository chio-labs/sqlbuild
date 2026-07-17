"""Build command plan text, runtime target, and completion output phases."""

from __future__ import annotations

import sys
from typing import TextIO

from sqlbuild.cli.commands._helpers.build_python_nodes.python_node_output import (
    python_node_results_failed,
)
from sqlbuild.cli.commands._helpers.check.core import check_results_failed
from sqlbuild.cli.commands.classes.build_progress_callbacks import format_build_footer
from sqlbuild.cli.commands.models import (
    BuildCommandRequest,
    BuildExecutionPreparation,
    BuildInvocation,
    BuildRunOutcome,
)
from sqlbuild.cli.output.main._build_execution_json import format_build_execution_json
from sqlbuild.cli.output.main._write_execution_json_output import write_execution_json_output
from sqlbuild.cli.output.main.plan import format_plan
from sqlbuild.cli.target_artifacts.main._write_python_check_runtime_target import (
    write_python_check_runtime_target,
)
from sqlbuild.cli.target_artifacts.main._write_runtime_target import write_runtime_target
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.python_nodes.models import PythonCheckExecutionResult


def write_build_plan_text(
    *,
    request: BuildCommandRequest,
    invocation: BuildInvocation,
    pipeline_result: CompilePipelineResult,
) -> None:
    """Write the formatted plan text to the plan stream."""

    plan_stream: TextIO = sys.stderr if request.debug or request.json_output else sys.stdout
    plan_text: str = format_plan(
        plan=pipeline_result.plan_output,
        full_refresh=request.full_refresh,
        use_color=invocation.use_color,
        python_plan_entries=pipeline_result.python_plan_entries,
    )
    plan_stream.write("\n" + plan_text + "\n\n")
    plan_stream.flush()


def write_build_runtime_targets(
    *,
    invocation: BuildInvocation,
    pipeline_result: CompilePipelineResult,
    outcome: BuildRunOutcome,
    check_results: tuple[PythonCheckExecutionResult, ...],
) -> None:
    """Write runtime and python-check runtime target artifacts."""

    write_runtime_target(
        target_dir=invocation.effective_project_dir / "target",
        plan_output=pipeline_result.plan_output,
        result=outcome.result,
    )
    write_python_check_runtime_target(
        target_dir=invocation.effective_project_dir / "target",
        results=check_results,
    )


def write_build_completion_output(
    *,
    request: BuildCommandRequest,
    invocation: BuildInvocation,
    pipeline_result: CompilePipelineResult,
    preparation: BuildExecutionPreparation,
    outcome: BuildRunOutcome,
    check_results: tuple[PythonCheckExecutionResult, ...],
) -> None:
    """Write the build footer and optional execution JSON output."""

    footer: str = format_build_footer(
        result=outcome.result,
        elapsed=preparation.callbacks.elapsed,
        use_color=invocation.use_color,
        python_node_results=outcome.python_results,
    )
    invocation.progress_stream.write("\n" + footer + "\n")
    invocation.progress_stream.flush()
    write_execution_json_output(
        payload=format_build_execution_json(
            result=outcome.result,
            plan=pipeline_result.plan_output,
            python_node_results=outcome.python_results,
            python_check_results=check_results,
        ),
        json_output=request.json_output,
        json_output_path=request.json_output_path,
    )


def resolve_build_exit_code(
    *,
    outcome: BuildRunOutcome,
    check_results: tuple[PythonCheckExecutionResult, ...],
) -> int:
    """Resolve the build exit code from execution, python, and check results."""

    python_failed: bool = python_node_results_failed(outcome.python_results)
    checks_failed: bool = check_results_failed(check_results)
    return (
        0
        if outcome.result.status == BuildStatus.SUCCESS and not python_failed and not checks_failed
        else 1
    )
