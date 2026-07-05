"""Seed command execution phases."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TextIO

from sqlbuild.cli.commands.helpers.seed.models import (
    SeedExecutionPreparation,
    SeedInvocation,
    SeedRunOutcome,
)
from sqlbuild.cli.commands.shared.helpers.progress.connection import ConnectionProgressReporter
from sqlbuild.executor.build.models import SeedExecutionResult
from sqlbuild.executor.build.types import ExecutionStatus
from sqlbuild.executor.pipeline.main.run import run_seed_pipeline
from sqlbuild.shared.helpers.output.cli_style import CliStyle
from sqlbuild.shared.main.coded_error_text import format_coded_error


def execute_seed_plan(
    *, invocation: SeedInvocation, preparation: SeedExecutionPreparation
) -> SeedRunOutcome:
    """Execute compiled seed entries."""

    start: float = time.monotonic()
    on_complete: Callable[[SeedExecutionResult], None] = _build_on_complete(
        stream=invocation.progress_stream,
        use_color=invocation.use_color,
        seed_order={
            seed_entry.name: index
            for index, seed_entry in enumerate(
                preparation.pipeline_result.plan_output.seed_entries, start=1
            )
        },
        total_count=len(preparation.pipeline_result.plan_output.seed_entries),
    )
    execution_connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=invocation.adapter_name,
        stream=invocation.progress_stream,
        blank_line_after_complete=True,
        use_color=invocation.use_color,
    )
    results: tuple[SeedExecutionResult, ...] = run_seed_pipeline(
        plan=preparation.pipeline_result.plan_output,
        connection_config=invocation.connection_config,
        adapter=invocation.adapter,
        max_concurrency=preparation.effective_concurrency,
        run_id=preparation.pipeline_result.project.run_id,
        query_change_tracking=preparation.pipeline_result.project.settings.query_change_tracking,
        on_seed_complete=on_complete,
        on_connection_start=execution_connection_progress.on_connection_start,
        on_connection_complete=execution_connection_progress.on_connection_complete,
        on_connection_error=execution_connection_progress.on_connection_error,
    )
    return SeedRunOutcome(results=results, elapsed=time.monotonic() - start)


def _build_on_complete(
    *, stream: TextIO, use_color: bool, seed_order: dict[str, int], total_count: int
) -> Callable[[SeedExecutionResult], None]:
    def _on_complete(result: SeedExecutionResult) -> None:
        status_text: str = "OK" if result.status == ExecutionStatus.SUCCESS else "FAIL"
        style: CliStyle = CliStyle(use_color=use_color)
        status: str = style.status(status_text)
        duration: str = ""
        if result.duration_ms is not None:
            seconds: float = result.duration_ms / 1000.0
            duration = f"{seconds:.2f}s"
        ordinal: int = seed_order[result.seed_name]
        stream.write(
            f"  {ordinal}/{total_count}  seed      {result.seed_name:<30} {status:<6} {duration}\n"
        )
        if result.error_message is not None:
            stream.write(f"    {_format_seed_error(result=result, use_color=use_color)}\n")
        stream.flush()

    return _on_complete


def _format_seed_error(*, result: SeedExecutionResult, use_color: bool) -> str:
    if result.error_message is None:
        return ""
    if result.error_code is None:
        return result.error_message
    return format_coded_error(
        code=result.error_code,
        message=result.error_message,
        help=result.error_help,
        use_color=use_color,
    )
