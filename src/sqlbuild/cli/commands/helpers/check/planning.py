"""Check command plan compilation phase."""

from __future__ import annotations

from sqlbuild.cli.commands.helpers.check.models import CheckCommandRequest, CheckInvocation
from sqlbuild.cli.commands.shared.helpers.connection.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult


def compile_check_plan(
    *, request: CheckCommandRequest, invocation: CheckInvocation
) -> CompilePipelineResult:
    """Compile the project for Python check execution."""

    return run_compile_pipeline(
        discovered_inputs=invocation.discovered_inputs,
        adapter=invocation.adapter,
        selected_target=request.selected_target,
        no_sql_validation=request.no_sql_validation,
        source_deferral_enabled=False,
        select=(),
        exclude=(),
        connection_config=invocation.connection_config,
        cli_vars=request.cli_vars,
        on_connection_start=invocation.connection_progress.on_connection_start,
        on_connection_complete=invocation.connection_progress.on_connection_complete,
        on_connection_error=invocation.connection_progress.on_connection_error,
        on_progress=invocation.planning_progress.on_progress,
        external_sql_reference_resolver=resolve_external_sql_reference_resolver(
            project_dir=invocation.effective_project_dir,
            discovered_inputs=invocation.discovered_inputs,
        ),
    )
