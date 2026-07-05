"""Load command execution phase."""

from __future__ import annotations

import time

from sqlbuild.cli.commands.helpers.load.models import (
    LoadCommandRequest,
    LoadExecutionPreparation,
    LoadInvocation,
    LoadRunOutcome,
)
from sqlbuild.cli.commands.helpers.load.progress import LoadProgressReporter
from sqlbuild.cli.commands.shared.helpers.config.parsers import (
    parse_cursor_integer,
    parse_cursor_timestamp,
)
from sqlbuild.cli.commands.shared.helpers.progress.connection import ConnectionProgressReporter
from sqlbuild.executor.load.main.run import run_load_pipeline
from sqlbuild.executor.load.models import LoadExecutionResult


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
            source.name: index
            for index, source in enumerate(invocation.selected_sources, start=1)
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
        run_id=preparation.run_id,
        runtime_dir=invocation.effective_project_dir / "target",
        target=preparation.target_name,
        vars=preparation.effective_vars,
        is_reload=request.reload,
        start_cursor_ts=parse_cursor_timestamp(preparation.effective_cursor_overrides.start_ts),
        end_cursor_ts=parse_cursor_timestamp(preparation.effective_cursor_overrides.end_ts),
        start_cursor_int=parse_cursor_integer(preparation.effective_cursor_overrides.start_int),
        end_cursor_int=parse_cursor_integer(preparation.effective_cursor_overrides.end_int),
        max_concurrency=preparation.effective_concurrency,
        on_load_start=load_progress.on_start,
        on_load_progress=load_progress.on_progress,
        on_load_complete=load_progress.on_complete,
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=connection_progress.on_connection_complete,
        on_connection_error=connection_progress.on_connection_error,
        use_color=invocation.use_color,
        providers=preparation.provider_session.providers,
    )
    return LoadRunOutcome(
        results=results,
        elapsed=time.monotonic() - start,
        success_count=sum(1 for result in results if result.status.value == "success"),
        fail_count=sum(1 for result in results if result.status.value == "failed"),
        skip_count=sum(1 for result in results if result.status.value == "skipped"),
    )
