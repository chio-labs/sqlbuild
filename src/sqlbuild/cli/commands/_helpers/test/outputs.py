"""Test command output writing and exit-code phases."""

from __future__ import annotations

from sqlbuild.cli.commands.models import TestCommandRequest, TestInvocation
from sqlbuild.cli.output.main.sql_test_execution_json import format_test_execution_json
from sqlbuild.cli.output.main.write_execution_json_output import write_execution_json_output
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.presentation.main.summary_footer import format_summary_footer


def write_test_completion_output(
    *,
    request: TestCommandRequest,
    invocation: TestInvocation,
    results: tuple[SqlTestExecutionResult, ...],
) -> None:
    """Write the test summary footer and optional JSON output."""

    pass_count: int = sum(1 for r in results if r.outcome == SqlTestOutcome.PASS)
    fail_count: int = len(results) - pass_count
    invocation.progress_stream.write(
        "\n"
        + format_summary_footer(
            counts=(
                ("PASS", pass_count),
                ("FAIL", fail_count),
                ("TOTAL", len(results)),
            ),
            use_color=invocation.use_color,
        )
        + "\n"
    )
    invocation.progress_stream.flush()
    write_execution_json_output(
        payload=format_test_execution_json(results=results),
        json_output=request.json_output,
        json_output_path=request.json_output_path,
    )


def resolve_test_exit_code(results: tuple[SqlTestExecutionResult, ...]) -> int:
    """Resolve the test exit code from failed test outcomes."""

    pass_count: int = sum(1 for r in results if r.outcome == SqlTestOutcome.PASS)
    return 0 if len(results) - pass_count == 0 else 1
