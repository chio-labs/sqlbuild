"""Seed command plan compilation phase."""

from __future__ import annotations

from sqlbuild.cli.commands.helpers.planning.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands.helpers.seed.models import (
    SeedCommandRequest,
    SeedExecutionPreparation,
    SeedInvocation,
)
from sqlbuild.cli.progress.classes.connection_progress_reporter import ConnectionProgressReporter
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import (
    CompilePipelineOptions,
    CompilePipelineResult,
)
from sqlbuild.shared.models import ConnectionHooks


def prepare_seed_execution(
    *, request: SeedCommandRequest, invocation: SeedInvocation
) -> SeedExecutionPreparation:
    """Compile seed plan and resolve effective concurrency."""

    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=invocation.adapter_name,
        stream=invocation.progress_stream,
        use_color=invocation.use_color,
    )
    invocation.progress_stream.write("\n")
    invocation.progress_stream.flush()
    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=invocation.discovered_inputs,
        adapter=invocation.adapter,
        options=CompilePipelineOptions(
            selected_target=request.selected_target,
            select=request.select,
            exclude=request.exclude,
            connection_config=invocation.connection_config,
            cli_vars=request.cli_vars,
            external_sql_reference_resolver=resolve_external_sql_reference_resolver(
                project_dir=invocation.effective_project_dir,
                discovered_inputs=invocation.discovered_inputs,
            ),
        ),
        hooks=ConnectionHooks(
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
    effective_concurrency: int = max(
        1,
        request.concurrency
        if request.concurrency is not None
        else pipeline_result.project.settings.concurrency,
    )
    return SeedExecutionPreparation(
        pipeline_result=pipeline_result,
        effective_concurrency=effective_concurrency,
    )
