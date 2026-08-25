"""CLI build command entry point."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from typing import Any

from sqlbuild.cli.commands._helpers.build_execution.checks import run_post_build_python_checks
from sqlbuild.cli.commands._helpers.build_execution.execution import (
    execute_build_plan,
    prepare_build_execution,
)
from sqlbuild.cli.commands._helpers.build_execution.no_work import (
    finalize_no_work_build_if_needed,
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
from sqlbuild.cli.commands._helpers.cost.collection import (
    finalize_build_cost,
    render_build_cost,
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
from sqlbuild.cost.models import CostRunRecord
from sqlbuild.cost.types import CostStatus
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
        if finalize_no_work_build_if_needed(
            request=request,
            invocation=invocation,
            pipeline_result=pipeline_result,
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
            preparation, outcome, check_results = _execute_standard_build(
                request=request,
                invocation=invocation,
                pipeline_result=pipeline_result,
                providers=provider_session.providers,
            )
        except BaseException as error:
            _ = _finalize_exceptional_standard_cost(
                invocation=invocation,
                pipeline_result=pipeline_result,
                build_started_at=build_started_at,
                error=error,
            )
            raise
        build_completed_at: datetime = datetime.now(UTC)
        exit_code: int = resolve_build_exit_code(outcome=outcome, check_results=check_results)
        write_build_runtime_targets(
            invocation=invocation,
            pipeline_result=pipeline_result,
            outcome=outcome,
            check_results=check_results,
        )
        cost_record: CostRunRecord | None = finalize_build_cost(
            BuildCostFinalization(
                project_dir=invocation.effective_project_dir,
                adapter_name=invocation.adapter_name,
                adapter=invocation.adapter,
                connection_config=invocation.connection_config,
                target_name=pipeline_result.project.effective_target_name,
                run_id=pipeline_result.project.run_id,
                build_status="success" if exit_code == 0 else "failed",
                started_at=build_started_at,
                completed_at=build_completed_at,
                config=invocation.discovered_inputs.project_config.cost,
                output_stream=invocation.progress_stream,
                use_color=invocation.use_color,
                render=False,
            )
        )
        write_build_completion_output(
            request=request,
            invocation=invocation,
            pipeline_result=pipeline_result,
            preparation=preparation,
            outcome=outcome,
            check_results=check_results,
            cost_record=cost_record,
        )
        _ = render_build_cost(
            record=cost_record,
            output_stream=invocation.progress_stream,
            use_color=invocation.use_color,
        )
        return exit_code
    finally:
        provider_session.close()


def _execute_standard_build(
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
            check_results: tuple[PythonCheckExecutionResult, ...] = run_post_build_python_checks(
                request=request,
                invocation=invocation,
                pipeline_result=pipeline_result,
                outcome=outcome,
                providers=providers,
            )
    return preparation, outcome, check_results


def _finalize_exceptional_standard_cost(
    *,
    invocation: BuildInvocation,
    pipeline_result: CompilePipelineResult,
    build_started_at: datetime,
    error: BaseException,
) -> None:
    interrupted: bool = isinstance(error, KeyboardInterrupt)
    try:
        _ = finalize_build_cost(
            BuildCostFinalization(
                project_dir=invocation.effective_project_dir,
                adapter_name=invocation.adapter_name,
                adapter=invocation.adapter,
                connection_config=invocation.connection_config,
                target_name=pipeline_result.project.effective_target_name,
                run_id=pipeline_result.project.run_id,
                build_status="interrupted" if interrupted else "failed",
                started_at=build_started_at,
                completed_at=datetime.now(UTC),
                config=invocation.discovered_inputs.project_config.cost,
                output_stream=invocation.progress_stream,
                use_color=invocation.use_color,
                collect=not interrupted,
                render=False,
                cost_status=CostStatus.PARTIAL,
                cost_message="Build was interrupted before cost collection completed.",
            )
        )
    except BaseException:
        return
