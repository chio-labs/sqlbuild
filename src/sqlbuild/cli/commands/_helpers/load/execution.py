"""Load command execution phase."""

from __future__ import annotations

import time

from sqlbuild.cli.commands._helpers.input.parsing import (
    parse_cursor_integer,
    parse_cursor_timestamp,
)
from sqlbuild.cli.commands._helpers.load.models import (
    LoadCommandRequest,
    LoadExecutionPreparation,
    LoadInvocation,
    LoadRunOutcome,
)
from sqlbuild.cli.commands.classes.load_progress_reporter import LoadProgressReporter
from sqlbuild.cli.progress.classes.connection_progress_reporter import ConnectionProgressReporter
from sqlbuild.executor.contracts.types import ExecutionStatus
from sqlbuild.executor.load.main.run import run_load_pipeline
from sqlbuild.executor.load.models import (
    LoadCallbacks,
    LoadExecutionResult,
    LoadRuntimeParams,
)


def execute_load_plan(
    *,
    request: LoadCommandRequest,
    invocation: LoadInvocation,
    preparation: LoadExecutionPreparation,
) -> LoadRunOutcome:
    """Execute selected source loads."""

    start: float = time.monotonic()
    load_progress: LoadProgressReporter = LoadProgressReporter(
        stream=invocation.progress_stream,
        use_color=invocation.use_color,
        source_order={
            source.name: index for index, source in enumerate(invocation.selected_sources, start=1)
        },
        total_count=len(invocation.selected_sources),
    )
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=preparation.adapter_name,
        stream=invocation.progress_stream,
        blank_line_after_complete=True,
        use_color=invocation.use_color,
    )
    results: tuple[LoadExecutionResult, ...] = run_load_pipeline(
        sources=invocation.selected_sources,
        reference_sources=invocation.reference_sources,
        loader_functions=invocation.discovered_inputs.loader_functions,
        connection_config=preparation.connection_config,
        adapter=preparation.adapter,
        max_concurrency=preparation.effective_concurrency,
        runtime=LoadRuntimeParams(
            run_id=preparation.run_id,
            runtime_dir=invocation.effective_project_dir / "target",
            target=preparation.target_name,
            vars=preparation.effective_vars,
            is_reload=request.reload,
            start_cursor_ts=parse_cursor_timestamp(preparation.effective_cursor_overrides.start_ts),
            end_cursor_ts=parse_cursor_timestamp(preparation.effective_cursor_overrides.end_ts),
            start_cursor_int=parse_cursor_integer(preparation.effective_cursor_overrides.start_int),
            end_cursor_int=parse_cursor_integer(preparation.effective_cursor_overrides.end_int),
            use_color=invocation.use_color,
            providers=preparation.provider_session.providers,
        ),
        callbacks=LoadCallbacks(
            on_load_start=load_progress.on_start,
            on_load_progress=lambda source, message: load_progress.on_progress(
                source=source, message=message
            ),
            on_load_complete=load_progress.on_complete,
            on_connection_start=connection_progress.on_connection_start,
            on_connection_complete=lambda connection_count, elapsed_seconds: (
                connection_progress.on_connection_complete(
                    connection_count=connection_count, elapsed_seconds=elapsed_seconds
                )
            ),
            on_connection_error=lambda connection_count, elapsed_seconds: (
                connection_progress.on_connection_error(
                    connection_count=connection_count, elapsed_seconds=elapsed_seconds
                )
            ),
        ),
    )
    return LoadRunOutcome(
        results=results,
        elapsed=time.monotonic() - start,
        success_count=sum(1 for result in results if result.status == ExecutionStatus.SUCCESS),
        fail_count=sum(1 for result in results if result.status == ExecutionStatus.FAILED),
        skip_count=sum(1 for result in results if result.status == ExecutionStatus.SKIPPED),
    )
