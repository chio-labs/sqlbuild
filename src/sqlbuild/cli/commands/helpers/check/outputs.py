"""Check command output writing and exit-code phases."""

from __future__ import annotations

from sqlbuild.cli.commands.helpers.check.core import format_check_json, write_check_results
from sqlbuild.cli.commands.helpers.check.models import (
    CheckCommandRequest,
    CheckExecutionPreparation,
    CheckInvocation,
)
from sqlbuild.cli.commands.shared.helpers.output.execution_json import write_execution_json_output
from sqlbuild.cli.commands.shared.helpers.targets.runtime import write_python_check_runtime_target
from sqlbuild.executor.python_nodes.models import PythonCheckExecutionResult
from sqlbuild.shared.main.summary_footer import format_summary_footer


def write_check_completion_output(
    *,
    request: CheckCommandRequest,
    invocation: CheckInvocation,
    preparation: CheckExecutionPreparation,
    results: tuple[PythonCheckExecutionResult, ...],
) -> None:
    """Write check rows, summary, runtime artifact, and optional JSON output."""

    write_check_results(
        stream=invocation.progress_stream,
        results=results,
        use_color=invocation.use_color,
        check_functions=preparation.check_functions,
        python_graph=preparation.python_graph,
    )
    invocation.progress_stream.write(
        "\n"
        + format_summary_footer(
            counts=(
                ("PASS", _pass_count(results)),
                ("WARN", _warn_count(results=results)),
                ("FAIL", _fail_count(results)),
                ("TOTAL", len(results)),
            ),
            use_color=invocation.use_color,
        )
        + "\n"
    )
    invocation.progress_stream.flush()
    write_python_check_runtime_target(
        target_dir=invocation.effective_project_dir / "target", results=results
    )
    write_execution_json_output(
        payload=format_check_json(results=results),
        json_output=request.json_output,
        json_output_path=request.json_output_path,
    )


def resolve_check_exit_code(results: tuple[PythonCheckExecutionResult, ...]) -> int:
    """Resolve the check exit code from failed Python check results."""

    return 0 if _fail_count(results) == 0 else 1


def _pass_count(results: tuple[PythonCheckExecutionResult, ...]) -> int:
    return sum(1 for result in results if result.passed)


def _warn_count(results: tuple[PythonCheckExecutionResult, ...]) -> int:
    return sum(1 for result in results if result.warned)


def _fail_count(results: tuple[PythonCheckExecutionResult, ...]) -> int:
    return sum(1 for result in results if result.failed)
