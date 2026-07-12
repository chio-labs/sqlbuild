"""Seed command output writing and exit-code phases."""

from __future__ import annotations

from sqlbuild.cli.commands.helpers.seed.models import (
    SeedCommandRequest,
    SeedExecutionPreparation,
    SeedInvocation,
    SeedRunOutcome,
)
from sqlbuild.cli.output.main.seed_execution_json import format_seed_execution_json
from sqlbuild.cli.output.main.write_execution_json_output import write_execution_json_output
from sqlbuild.cli.progress.main.write_execution_header import write_execution_header
from sqlbuild.executor.build.models import SeedExecutionResult
from sqlbuild.executor.build.types import ExecutionStatus
from sqlbuild.shared.helpers.output.cli_style import CliStyle
from sqlbuild.shared.main.summary_footer import format_summary_footer


def write_seed_execution_header(
    *, invocation: SeedInvocation, preparation: SeedExecutionPreparation
) -> None:
    """Write seed ready, selected seed names, and execution headers."""

    seed_count: int = len(preparation.pipeline_result.plan_output.seed_entries)
    style: CliStyle = CliStyle(use_color=invocation.use_color)
    ready_header: str = f"Seed ready ({seed_count} selected)"
    invocation.progress_stream.write(f"\n{style.success_strong(ready_header)}\n\n")
    invocation.progress_stream.write(f"{style.success_strong(f'Seeds ({seed_count})')}\n")
    for seed_entry in preparation.pipeline_result.plan_output.seed_entries:
        invocation.progress_stream.write(f"  {seed_entry.name}\n")
    invocation.progress_stream.write("\n")
    write_execution_header(
        stream=invocation.progress_stream,
        command="sqb seed",
        target=None,
        concurrency=preparation.effective_concurrency,
        use_color=invocation.use_color,
    )


def write_seed_completion_output(
    *,
    request: SeedCommandRequest,
    invocation: SeedInvocation,
    preparation: SeedExecutionPreparation,
    outcome: SeedRunOutcome,
) -> None:
    """Write seed summary and optional JSON output."""

    success_count: int = _success_count(outcome.results)
    fail_count: int = _fail_count(outcome.results)
    completion_message: str = (
        "Completed successfully." if fail_count == 0 else "Completed with errors."
    )
    invocation.progress_stream.write(f"\n{completion_message}\n")
    invocation.progress_stream.write(
        format_summary_footer(
            counts=(
                ("PASS", success_count),
                ("WARN", 0),
                ("FAIL", fail_count),
                ("SKIP", 0),
                ("TOTAL", len(outcome.results)),
            ),
            use_color=invocation.use_color,
            elapsed=f"{outcome.elapsed:.2f}s",
        )
        + "\n"
    )
    invocation.progress_stream.flush()
    write_execution_json_output(
        payload=format_seed_execution_json(
            results=outcome.results,
            plan=preparation.pipeline_result.plan_output,
        ),
        json_output=request.json_output,
        json_output_path=request.json_output_path,
    )


def resolve_seed_exit_code(results: tuple[SeedExecutionResult, ...]) -> int:
    """Resolve seed exit code from failed results."""

    return 0 if _fail_count(results) == 0 else 1


def _success_count(results: tuple[SeedExecutionResult, ...]) -> int:
    return sum(1 for result in results if result.status == ExecutionStatus.SUCCESS)


def _fail_count(results: tuple[SeedExecutionResult, ...]) -> int:
    return sum(1 for result in results if result.status == ExecutionStatus.FAILED)
