"""Plan command pipeline compilation phase."""

from __future__ import annotations

from sqlbuild.cli.commands.helpers.plan.models import PlanCommandRequest, PlanInvocation
from sqlbuild.cli.commands.shared.helpers.connection.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import (
    CompilePipelineOptions,
    CompilePipelineResult,
)
from sqlbuild.shared.models import ConnectionHooks
from sqlbuild.virtual.planner.main.plan import run_virtual_plan_pipeline
from sqlbuild.virtual.planner.models import VirtualPlanOptions


def compile_plan_pipeline(
    *,
    request: PlanCommandRequest,
    invocation: PlanInvocation,
) -> CompilePipelineResult:
    """Compile the plan pipeline in virtual or standard mode."""

    external_sql_reference_resolver: object | None = resolve_external_sql_reference_resolver(
        project_dir=invocation.effective_project_dir,
        discovered_inputs=invocation.discovered_inputs,
    )
    if invocation.virtual_mode:
        return run_virtual_plan_pipeline(
            project_dir=invocation.effective_project_dir,
            discovered_inputs=invocation.discovered_inputs,
            adapter=invocation.adapter,
            connection_config=invocation.connection_config,
            options=VirtualPlanOptions(
                selected_target=request.selected_target,
                no_sql_validation=request.no_sql_validation,
                defer_sources_to=request.defer_sources_to,
                cursor_overrides=request.cursor_overrides,
                full_refresh=request.full_refresh,
                virtual_environment_name=request.virtual_env,
                include_stale_upstreams=request.include_stale_upstreams,
                changes_only=not invocation.effective_force,
                auto_load_sources=invocation.should_load_sources,
                include_python=request.include_python,
                select=request.select,
                exclude=request.exclude,
                cli_vars=request.cli_vars,
                external_sql_reference_resolver=external_sql_reference_resolver,
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
    return run_compile_pipeline(
        discovered_inputs=invocation.discovered_inputs,
        adapter=invocation.adapter,
        options=CompilePipelineOptions(
            selected_target=request.selected_target,
            no_sql_validation=request.no_sql_validation,
            defer_to=request.defer_to,
            defer_sources_to=request.defer_sources_to,
            cursor_overrides=request.cursor_overrides,
            full_refresh=request.full_refresh,
            changes_only=not invocation.effective_force,
            auto_load_sources=invocation.should_load_sources,
            select=request.select,
            exclude=request.exclude,
            connection_config=invocation.connection_config,
            cli_vars=request.cli_vars,
            external_sql_reference_resolver=external_sql_reference_resolver,
            resolve_python_run_selectors=request.include_python,
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
