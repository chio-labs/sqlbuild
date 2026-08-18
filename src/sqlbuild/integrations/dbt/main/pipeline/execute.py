"""Runtime execution pipeline for ordinary dbt interop commands."""

from __future__ import annotations

from sqlbuild.compiler.pipeline.main.plan_work import plan_has_executable_work
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.integrations.dbt._helpers.pipeline.execute import (
    build_failed_sqlbuild_model_names,
    build_merged_dbt_execution_argv,
)
from sqlbuild.integrations.dbt._helpers.pipeline.execution_phases import (
    execute_dbt_without_state_tracking,
    resolve_dbt_connection_config,
    resolve_sqlbuild_execution_plan_output,
    run_dbt_sqlbuild_work,
    write_dbt_execution_plan_text,
    write_dbt_execution_summary,
    write_sqlbuild_skip_notice,
)
from sqlbuild.integrations.dbt._helpers.pipeline.interop_prologue import (
    compile_dbt_interop_project,
    load_compiled_dbt_manifest,
    resolve_dbt_execution_invocation,
    resolve_dbt_interop_plan,
)
from sqlbuild.integrations.dbt.exceptions import DbtInteropArgumentError
from sqlbuild.integrations.dbt.models import (
    DbtCommandExecutionResult,
    DbtInteropCompiledProject,
    DbtInteropExecutionRequest,
    DbtInteropInvocation,
    DbtInteropPlanResolution,
    DbtManifestIndex,
)
from sqlbuild.integrations.dbt.types import DbtInteropCommand


def execute_dbt_interop_from_project(request: DbtInteropExecutionRequest) -> int:
    """Execute dbt first, then native SQLBuild work selected by the combined graph."""

    if request.command not in (
        DbtInteropCommand.RUN,
        DbtInteropCommand.BUILD,
    ):
        raise DbtInteropArgumentError(
            f"unsupported dbt interop execution command: {request.command}"
        )
    invocation: DbtInteropInvocation = resolve_dbt_execution_invocation(request)
    manifest: DbtManifestIndex = load_compiled_dbt_manifest(
        runner=invocation.runner,
        dbt_options=invocation.dbt_options,
        full_refresh=False,
        on_progress=request.on_progress,
    )
    compiled: DbtInteropCompiledProject = compile_dbt_interop_project(
        project_dir=request.project_dir,
        discovered_inputs=invocation.discovered_inputs,
        manifest=manifest,
        dbt_vars=invocation.dbt_vars,
        no_sql_validation=request.no_sql_validation,
        on_progress=request.on_progress,
    )
    resolution: DbtInteropPlanResolution = resolve_dbt_interop_plan(
        command=request.command,
        invocation=invocation,
        compiled=compiled,
        manifest=manifest,
        sqlbuild_executable=request.sqlbuild_executable,
        on_progress=request.on_progress,
    )
    merged_dbt_argv: tuple[str, ...] | None = build_merged_dbt_execution_argv(
        command=request.command,
        options=invocation.dbt_options,
        routed_args=invocation.routed.dbt_args,
        plan=resolution.plan,
    )
    write_dbt_execution_plan_text(
        request=request,
        invocation=invocation,
        plan=resolution.plan,
        merged_dbt_argv=merged_dbt_argv,
    )
    execution: DbtCommandExecutionResult = execute_dbt_without_state_tracking(
        request=request,
        invocation=invocation,
        merged_dbt_argv=merged_dbt_argv,
    )
    write_dbt_execution_summary(
        request=request,
        invocation=invocation,
        execution=execution,
    )
    failed_sqlbuild_model_names: tuple[str, ...] = build_failed_sqlbuild_model_names(
        graph=resolution.graph,
        manifest=manifest,
        node_results=execution.node_results,
    )
    if execution.returncode != 0 and not execution.node_results:
        return execution.returncode
    plan_output: PlanOutput | None = resolve_sqlbuild_execution_plan_output(
        request=request,
        invocation=invocation,
        compiled=compiled,
        manifest=manifest,
        plan=resolution.plan,
        failed_sqlbuild_model_names=failed_sqlbuild_model_names,
    )
    if plan_output is None:
        if resolution.plan.sqlbuild_skip_reason is not None:
            write_sqlbuild_skip_notice(
                request=request,
                invocation=invocation,
                message="No SQLBuild work selected.",
            )
        return execution.returncode
    if not plan_has_executable_work(plan=plan_output):
        write_sqlbuild_skip_notice(
            request=request,
            invocation=invocation,
            message="Skipping SQLBuild: no executable work selected.",
        )
        return execution.returncode
    connection_config: dict[str, object] = resolve_dbt_connection_config(
        request=request,
        invocation=invocation,
        compiled=compiled,
    )
    sqlbuild_exit_code: int = run_dbt_sqlbuild_work(
        request=request,
        invocation=invocation,
        compiled=compiled,
        plan_output=plan_output,
        connection_config=connection_config,
    )
    return max(execution.returncode, sqlbuild_exit_code)
