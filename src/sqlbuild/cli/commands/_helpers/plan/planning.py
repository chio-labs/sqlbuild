"""Plan command pipeline compilation phase."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.planning.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands.models import PlanCommandRequest, PlanInvocation
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import (
    CompilePipelineOptions,
    CompilePipelineResult,
)
from sqlbuild.runtime.contracts.models import ConnectionHooks


def compile_plan_pipeline(
    *,
    request: PlanCommandRequest,
    invocation: PlanInvocation,
) -> CompilePipelineResult:
    """Compile the plan pipeline."""

    external_sql_reference_resolver: object | None = resolve_external_sql_reference_resolver(
        project_dir=invocation.effective_project_dir,
        discovered_inputs=invocation.discovered_inputs,
    )
    if request.as_target is not None:
        invocation.progress_stream.write(
            f"Previewing plan as target '{request.as_target}' through the active target's "
            "connection (inspection only).\n"
        )
        invocation.progress_stream.flush()
    result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=invocation.discovered_inputs,
        adapter=invocation.adapter,
        options=CompilePipelineOptions(
            selected_target=(
                request.as_target if request.as_target is not None else request.selected_target
            ),
            no_sql_validation=request.no_sql_validation,
            no_cache=request.no_cache,
            defer_to=request.defer_to,
            defer_sources_to=request.defer_sources_to,
            cursor_overrides=request.cursor_overrides,
            full_refresh=request.full_refresh,
            auto_load_sources=invocation.should_load_sources,
            select=request.select,
            exclude=request.exclude,
            connection_config=invocation.connection_config,
            cli_vars=request.cli_vars,
            external_sql_reference_resolver=external_sql_reference_resolver,
            resolve_python_run_selectors=request.include_python,
            max_microbatches=request.max_microbatches,
            selection_diagnostics=request.selection_diagnostics,
        ),
        hooks=ConnectionHooks(
            on_progress=invocation.planning_progress.on_progress,
            on_connection_start=invocation.connection_progress.on_connection_start,
            on_connection_complete=lambda connection_count, elapsed_seconds: (
                invocation.connection_progress.on_connection_complete(
                    connection_count=connection_count, elapsed_seconds=elapsed_seconds
                )
            ),
            on_connection_error=lambda connection_count, elapsed_seconds: (
                invocation.connection_progress.on_connection_error(
                    connection_count=connection_count, elapsed_seconds=elapsed_seconds
                )
            ),
        ),
    )
    return result
