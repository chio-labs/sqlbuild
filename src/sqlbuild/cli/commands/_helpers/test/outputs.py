"""Test command output writing and exit-code phases."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.test.sql_progress import format_parameterized_test_label
from sqlbuild.cli.commands.models import TestCommandRequest, TestInvocation
from sqlbuild.cli.output.main._sql_test_execution_json import format_test_execution_json
from sqlbuild.cli.output.main._write_execution_json_output import write_execution_json_output
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.main.coded_error_text import format_coded_error
from sqlbuild.presentation.main.summary_footer import format_summary_footer

_ERROR_LABEL_WIDTH: int = 10


def write_test_completion_output(
    *,
    request: TestCommandRequest,
    invocation: TestInvocation,
    results: tuple[SqlTestExecutionResult, ...],
) -> None:
    """Write the test summary footer and optional JSON output."""

    pass_count: int = sum(1 for r in results if r.outcome == SqlTestOutcome.PASS)
    fail_count: int = len(results) - pass_count
    summary: str = format_summary_footer(
        counts=(
            ("PASS", pass_count),
            ("FAIL", fail_count),
            ("TOTAL", len(results)),
        ),
        use_color=invocation.use_color,
    )
    failure_details: str = _format_test_failure_details(
        results=results,
        use_color=invocation.use_color,
    )
    rendered: str = f"\n{summary}"
    if failure_details:
        rendered = f"{rendered}\n\n{failure_details}"
    invocation.progress_stream.write(f"{rendered}\n")
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


def _format_test_failure_details(
    *, results: tuple[SqlTestExecutionResult, ...], use_color: bool
) -> str:
    failed_results: tuple[SqlTestExecutionResult, ...] = tuple(
        result for result in results if result.outcome != SqlTestOutcome.PASS
    )
    if not failed_results:
        return ""
    style: CliStyle = CliStyle(use_color=use_color)
    lines: list[str] = [style.error_strong("Failures:"), ""]
    result: SqlTestExecutionResult
    for result in failed_results:
        lines.append(
            "  "
            + format_parameterized_test_label(
                name=result.test_name,
                source_path=result.source_path,
                parameter_schema=result.parameter_schema,
                parameter_values=result.parameter_values,
            )
        )
        error_message: str = result.error_message or "test failed"
        rendered_error: str = error_message
        if result.error_code is not None:
            rendered_error = format_coded_error(
                code=result.error_code,
                message=error_message,
                help=result.error_help,
                use_color=use_color,
                include_error_label=False,
            )
        label: str = style.error_muted(f"{'error':<{_ERROR_LABEL_WIDTH}}")
        error_line: str
        for index, error_line in enumerate(rendered_error.splitlines() or [rendered_error]):
            display_label: str = label if index == 0 else " " * _ERROR_LABEL_WIDTH
            lines.append(f"    {display_label}{error_line}")
        lines.append("")
    return "\n".join(lines).rstrip()
