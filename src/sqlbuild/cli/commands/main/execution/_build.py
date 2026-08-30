"""CLI build command entry point."""

from __future__ import annotations

import sys
import time
from datetime import UTC, datetime
from typing import Any

from sqlbuild.cli.commands._helpers.build_execution.checks import run_post_build_python_checks
from sqlbuild.cli.commands._helpers.build_execution.completion import complete_direct_build
from sqlbuild.cli.commands._helpers.build_execution.execution import (
    execute_build_plan,
    prepare_build_execution,
)
from sqlbuild.cli.commands._helpers.build_execution.outputs import (
    write_build_plan_text,
)
from sqlbuild.cli.commands._helpers.build_execution.phase_timings import (
    finalize_exceptional_with_timings,
    finalize_no_work_with_timings,
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
from sqlbuild.cli.commands._helpers.cost.collection import (
    finalize_build_cost,
)
from sqlbuild.cli.commands.main.execution._virtual_build import run_virtual_build
from sqlbuild.cli.commands.models import (
    BuildCommandRequest,
    BuildCostFinalization,
    BuildExecutionPreparation,
    BuildInvocation,
    BuildRunOutcome,
    VirtualBuildCliRequest,
)
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.cost.classes.cost_context import CostContext
from sqlbuild.cost.types import CostStatus
from sqlbuild.diagnostics.classes.process_resource_tracker import ProcessResourceTracker
from sqlbuild.diagnostics.main.log_process_resources import log_process_resources
from sqlbuild.executor.python_nodes.models import PythonCheckExecutionResult
from sqlbuild.provider.main.session import build_provider_session


def run_build(request: BuildCommandRequest) -> int:
    """Execute the build command."""

    process_tracker: ProcessResourceTracker | None = (
        ProcessResourceTracker() if request.debug else None
    )
    try:
        return _run_build(request=request)
    finally:
        if process_tracker is not None:
            log_process_resources(usage=process_tracker.finish())


def _run_build(*, request: BuildCommandRequest) -> int:
    command_started_at: float = time.monotonic()
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
                    no_cache=request.no_cache,
                    defer_sources_to=request.defer_sources_to,
                    cursor_overrides=request.cursor_overrides,
                    full_refresh=request.full_refresh,
                    virtual_environment_name=request.virtual_env,
                    include_stale_upstreams=request.include_stale_upstreams,
                    changes_only=invocation.effective_changes_only,
                    auto_load_sources=invocation.should_load_sources,
                    reload_sources=request.reload_sources,
                    include_python=request.include_python,
                    select=request.select,
                    selector_files=request.selector_files,
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
                    command_started_at=command_started_at,
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
        if finalize_no_work_with_timings(
            request=request,
            invocation=invocation,
            pipeline_result=pipeline_result,
            command_started_at=command_started_at,
        ):
            return 0
        build_started_at: datetime = datetime.now(UTC)
        _ = finalize_build_cost(
            BuildCostFinalization(
                project_dir=invocation.effective_project_dir,
                adapter_name=invocation.adapter_name,
                adapter=invocation.adapter,
                connection_config=invocation.connection_config,
                target_name=pipeline_result.project.effective_target_name,
                target_database=pipeline_result.project.effective_target_database,
                run_id=pipeline_result.project.run_id,
                build_status="running",
                started_at=build_started_at,
                completed_at=build_started_at,
                config=invocation.discovered_inputs.project_config.cost,
                output_stream=invocation.progress_stream,
                use_color=invocation.use_color,
                collect=False,
                render=False,
                cost_status=CostStatus.PENDING,
                cost_message="Build cost collection has not completed.",
            )
        )
        try:
            preparation, outcome, check_results = _execute_direct_build(
                request=request,
                invocation=invocation,
                pipeline_result=pipeline_result,
                providers=provider_session.providers,
            )
        except BaseException as error:
            _ = finalize_exceptional_with_timings(
                request=request,
                invocation=invocation,
                pipeline_result=pipeline_result,
                build_started_at=build_started_at,
                command_started_at=command_started_at,
                error=error,
            )
            raise
        return complete_direct_build(
            request=request,
            invocation=invocation,
            pipeline_result=pipeline_result,
            preparation=preparation,
            outcome=outcome,
            check_results=check_results,
            build_started_at=build_started_at,
            command_started_at=command_started_at,
        )
    finally:
        provider_session.close()


def _execute_direct_build(
    *,
    request: BuildCommandRequest,
    invocation: BuildInvocation,
    pipeline_result: CompilePipelineResult,
    providers: Any,
) -> tuple[
    BuildExecutionPreparation,
    BuildRunOutcome,
    tuple[PythonCheckExecutionResult, ...],
]:
    with CostContext.scope(
        run_id=pipeline_result.project.run_id,
        resource_type="run",
        resource_name=(pipeline_result.project.effective_target_name or invocation.adapter_name),
        ledger_path=(
            invocation.effective_project_dir
            / "target"
            / "runs"
            / pipeline_result.project.run_id
            / "statements.jsonl"
        ),
        phase="build",
    ):
        preparation: BuildExecutionPreparation = prepare_build_execution(
            request=request,
            invocation=invocation,
            pipeline_result=pipeline_result,
            providers=providers,
        )
        try:
            outcome: BuildRunOutcome = execute_build_plan(
                request=request,
                invocation=invocation,
                pipeline_result=pipeline_result,
                preparation=preparation,
                providers=providers,
            )
            with CostContext.resource_scope(
                resource_type="run",
                resource_name=(
                    pipeline_result.project.effective_target_name or invocation.adapter_name
                ),
                phase="post_build_checks",
            ):
                check_results: tuple[PythonCheckExecutionResult, ...] = (
                    run_post_build_python_checks(
                        request=request,
                        invocation=invocation,
                        pipeline_result=pipeline_result,
                        outcome=outcome,
                        providers=providers,
                        preparation=preparation,
                    )
                )
        finally:
            preparation.callbacks.close()
    return preparation, outcome, check_results
