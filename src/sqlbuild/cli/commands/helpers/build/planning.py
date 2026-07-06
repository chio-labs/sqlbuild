"""Build command compile pipeline phase."""

from __future__ import annotations

from sqlbuild.cli.commands.helpers.build.models import BuildCommandRequest, BuildInvocation
from sqlbuild.cli.commands.shared.helpers.connection.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import (
    CompilePipelineOptions,
    CompilePipelineResult,
)
from sqlbuild.shared.models import ConnectionHooks


def compile_build_plan(
    *,
    request: BuildCommandRequest,
    invocation: BuildInvocation,
) -> CompilePipelineResult:
    """Run the compile pipeline for the build command."""

    invocation.progress_stream.write("\n")
    invocation.progress_stream.flush()
    return run_compile_pipeline(
        discovered_inputs=invocation.discovered_inputs,
        adapter=invocation.adapter,
        options=CompilePipelineOptions(
            no_sql_validation=request.no_sql_validation,
            selected_target=request.selected_target,
            defer_to=request.defer_to,
            defer_sources_to=request.defer_sources_to,
            cursor_overrides=request.cursor_overrides,
            select=request.select,
            exclude=request.exclude,
            full_refresh=request.full_refresh,
            changes_only=not invocation.effective_force,
            auto_load_sources=invocation.should_load_sources,
            reload_sources=request.reload_sources,
            connection_config=invocation.connection_config,
            cli_vars=request.cli_vars,
            external_sql_reference_resolver=resolve_external_sql_reference_resolver(
                project_dir=invocation.effective_project_dir,
                discovered_inputs=invocation.discovered_inputs,
            ),
            resolve_python_run_selectors=(request.include_python or invocation.should_load_sources),
        ),
        hooks=ConnectionHooks(
            on_progress=invocation.planning_progress.on_progress,
            on_connection_start=invocation.connection_progress.on_connection_start,
            on_connection_complete=invocation.connection_progress.on_connection_complete,
            on_connection_error=invocation.connection_progress.on_connection_error,
        ),
    )
