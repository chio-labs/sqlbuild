"""Audit command plan compilation phase."""

from __future__ import annotations

from sqlbuild.cli.commands.helpers.audit.models import AuditCommandRequest, AuditInvocation
from sqlbuild.cli.commands.shared.helpers.connection.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import (
    CompilePipelineOptions,
    CompilePipelineResult,
)
from sqlbuild.shared.models import ConnectionHooks


def compile_audit_plan(
    *,
    request: AuditCommandRequest,
    invocation: AuditInvocation,
) -> CompilePipelineResult:
    """Compile the audit plan for the selected scope."""

    return run_compile_pipeline(
        discovered_inputs=invocation.discovered_inputs,
        adapter=invocation.adapter,
        options=CompilePipelineOptions(
            selected_target=request.selected_target,
            no_sql_validation=request.no_sql_validation,
            defer_to=request.defer_to,
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
            on_progress=invocation.planning_progress.on_progress,
            on_connection_start=invocation.connection_progress.on_connection_start,
            on_connection_complete=invocation.connection_progress.on_connection_complete,
            on_connection_error=invocation.connection_progress.on_connection_error,
        ),
    )
