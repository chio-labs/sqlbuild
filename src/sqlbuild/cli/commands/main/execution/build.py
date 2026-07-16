"""CLI build command entry point."""

from __future__ import annotations

import sys
from typing import Any

from sqlbuild.cli.commands._helpers.build_execution.checks import run_post_build_python_checks
from sqlbuild.cli.commands._helpers.build_execution.execution import (
    execute_build_plan,
    prepare_build_execution,
)
from sqlbuild.cli.commands._helpers.build_execution.outputs import (
    resolve_build_exit_code,
    write_build_completion_output,
    write_build_plan_text,
    write_build_runtime_targets,
)
from sqlbuild.cli.commands._helpers.build_planning.compile_target import write_build_compile_target
from sqlbuild.cli.commands._helpers.build_planning.defer_clone import (
    run_defer_clone_boundary_prephase,
)
from sqlbuild.cli.commands._helpers.build_planning.full_refresh import (
    enforce_snapshot_full_refresh_policy,
)
from sqlbuild.cli.commands._helpers.build_planning.invocation import resolve_build_invocation
from sqlbuild.cli.commands._helpers.build_planning.planning import compile_build_plan
from sqlbuild.cli.commands.main.execution.virtual_build import run_virtual_build
from sqlbuild.cli.commands.models import (
    BuildCommandRequest,
    BuildExecutionPreparation,
    BuildInvocation,
    BuildRunOutcome,
    VirtualBuildCliRequest,
)
from sqlbuild.compiler.pipeline.main.plan_work import plan_has_executable_work
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.executor.python_nodes.models import PythonCheckExecutionResult
from sqlbuild.provider.main.session import build_provider_session


def run_build(request: BuildCommandRequest) -> int:
    """Execute the build command."""

    invocation: BuildInvocation = resolve_build_invocation(request=request)
    provider_session: Any = build_provider_session(
        discovered_providers=invocation.discovered_inputs.providers
    )
    try:
        if invocation.virtual_mode:
            return run_virtual_build(
                project_dir=invocation.effective_project_dir,
                discovered_inputs=invocation.discovered_inputs,
                adapter=invocation.adapter,
                adapter_name=invocation.adapter_name,
                connection_config=invocation.connection_config,
                progress_stream=invocation.progress_stream,
                request=VirtualBuildCliRequest(
                    selected_target=request.selected_target,
                    no_sql_validation=request.no_sql_validation,
                    defer_sources_to=request.defer_sources_to,
                    cursor_overrides=request.cursor_overrides,
                    full_refresh=request.full_refresh,
                    virtual_environment_name=request.virtual_env,
                    include_stale_upstreams=request.include_stale_upstreams,
                    changes_only=not invocation.effective_force,
                    auto_load_sources=invocation.should_load_sources,
                    reload_sources=request.reload_sources,
                    include_python=request.include_python,
                    select=request.select,
                    exclude=request.exclude,
                    fail_fast=request.fail_fast,
                    allow_snapshot_full_refresh=request.allow_snapshot_full_refresh,
                    allow_snapshot_schema_change=request.allow_snapshot_schema_change,
                    concurrency=request.concurrency,
                    verbose=request.verbose,
                    debug=request.debug,
                    cli_vars=request.cli_vars,
                    run_tests=request.run_tests,
                    run_audits=request.run_audits,
                    json_output=request.json_output,
                    json_output_path=request.json_output_path,
                    use_color=invocation.use_color,
                    providers=provider_session.providers,
                ),
            )
        if invocation.effective_defer_clone_from is not None:
            _ = run_defer_clone_boundary_prephase(
                request=request,
                invocation=invocation,
                origin_target_name=invocation.effective_defer_clone_from,
            )
        pipeline_result: CompilePipelineResult = compile_build_plan(
            request=request,
            invocation=invocation,
        )
        write_build_plan_text(
            request=request,
            invocation=invocation,
            pipeline_result=pipeline_result,
        )
        enforce_snapshot_full_refresh_policy(
            plan=pipeline_result.plan_output,
            snapshots_config=invocation.discovered_inputs.project_config.snapshots,
            allow_snapshot_full_refresh=request.allow_snapshot_full_refresh,
            input_stream=sys.stdin,
            output_stream=sys.stdout,
        )
        write_build_compile_target(
            request=request,
            invocation=invocation,
            pipeline_result=pipeline_result,
        )
        if not plan_has_executable_work(
            plan=pipeline_result.plan_output,
            python_plan_entries=pipeline_result.python_plan_entries,
        ):
            return 0
        preparation: BuildExecutionPreparation = prepare_build_execution(
            request=request,
            invocation=invocation,
            pipeline_result=pipeline_result,
            providers=provider_session.providers,
        )
        outcome: BuildRunOutcome = execute_build_plan(
            request=request,
            invocation=invocation,
            pipeline_result=pipeline_result,
            preparation=preparation,
            providers=provider_session.providers,
        )
        check_results: tuple[PythonCheckExecutionResult, ...] = run_post_build_python_checks(
            request=request,
            invocation=invocation,
            pipeline_result=pipeline_result,
            outcome=outcome,
            providers=provider_session.providers,
        )
        write_build_runtime_targets(
            invocation=invocation,
            pipeline_result=pipeline_result,
            outcome=outcome,
            check_results=check_results,
        )
        write_build_completion_output(
            request=request,
            invocation=invocation,
            pipeline_result=pipeline_result,
            preparation=preparation,
            outcome=outcome,
            check_results=check_results,
        )
        return resolve_build_exit_code(outcome=outcome, check_results=check_results)
    finally:
        provider_session.close()
