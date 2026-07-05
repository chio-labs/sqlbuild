"""Runtime execution pipeline for dbt interop execution commands."""

from __future__ import annotations

from sqlbuild.compiler.pipeline.main.plan_work import plan_has_executable_work
from sqlbuild.integrations.dbt.exceptions import DbtInteropArgumentError
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtDeferClonePlan,
    DbtExecutionOutcome,
    DbtInteropCompiledProject,
    DbtInteropExecutionRequest,
    DbtInteropInvocation,
    DbtInteropPlanResolution,
    DbtPlannedWork,
    DbtPreExecutionOutputs,
    DbtSqlbuildReplanResult,
    DbtTrackedExecution,
    DbtWriteIdentities,
)
from sqlbuild.integrations.dbt.pipeline.helpers.execute import (
    build_dbt_execution_outcome,
    build_merged_dbt_execution_argv,
)
from sqlbuild.integrations.dbt.pipeline.helpers.execution_phases import (
    build_dbt_write_identities,
    execute_dbt_with_state_tracking,
    finalize_dbt_interop_exit,
    resolve_dbt_defer_clone_plan,
    resolve_dbt_planned_work,
    resolve_dbt_pre_execution_outputs,
    resolve_sqlbuild_execution_plan_output,
    run_dbt_defer_clone_prephases,
    run_dbt_sqlbuild_work,
    write_dbt_execution_plan_text,
    write_dbt_execution_summary,
    write_sqlbuild_skip_notice,
)
from sqlbuild.integrations.dbt.pipeline.helpers.interop_prologue import (
    compile_dbt_interop_project,
    load_compiled_dbt_manifest,
    resolve_dbt_execution_invocation,
    resolve_dbt_interop_plan,
)
from sqlbuild.integrations.dbt.types import DbtInteropCommand


def execute_dbt_interop_from_project(request: DbtInteropExecutionRequest) -> int:
    """Execute dbt first, then SQLBuild, for downstream-only interop commands."""

    if request.command not in (
        DbtInteropCommand.RUN,
        DbtInteropCommand.BUILD,
        DbtInteropCommand.TEST,
    ):
        raise DbtInteropArgumentError(
            f"unsupported dbt interop execution command: {request.command}"
        )
    invocation: DbtInteropInvocation = resolve_dbt_execution_invocation(request)
    manifest: DbtManifestIndex = load_compiled_dbt_manifest(
        runner=invocation.runner,
        dbt_options=invocation.dbt_options,
        full_refresh=request.command == DbtInteropCommand.TEST,
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
    planned: DbtPlannedWork = resolve_dbt_planned_work(
        request=request,
        invocation=invocation,
        compiled=compiled,
        manifest=manifest,
        graph=resolution.graph,
        plan=resolution.plan,
    )
    identities: DbtWriteIdentities = build_dbt_write_identities(
        manifest=manifest,
        graph=resolution.graph,
        plan=planned.plan,
    )
    defer_clone: DbtDeferClonePlan = resolve_dbt_defer_clone_plan(
        invocation=invocation,
        compiled=compiled,
        manifest=manifest,
        graph=resolution.graph,
        plan=planned.plan,
    )
    merged_dbt_argv: tuple[str, ...] | None = build_merged_dbt_execution_argv(
        command=request.command,
        options=invocation.dbt_options,
        routed_args=invocation.routed.dbt_args,
        plan=planned.plan,
        replay_on_change=invocation.discovered_inputs.project_config.dbt.replay_on_change,
        defer_clone_unique_ids=defer_clone.unique_ids,
    )
    pre_execution: DbtPreExecutionOutputs = resolve_dbt_pre_execution_outputs(
        request=request,
        invocation=invocation,
        compiled=compiled,
        manifest=manifest,
        graph=resolution.graph,
        plan=planned.plan,
        defer_clone=defer_clone,
        merged_dbt_argv=merged_dbt_argv,
    )
    write_dbt_execution_plan_text(
        request=request,
        invocation=invocation,
        plan=pre_execution.plan,
        merged_dbt_argv=merged_dbt_argv,
    )
    prephase_exit: int | None = run_dbt_defer_clone_prephases(
        request=request,
        invocation=invocation,
        compiled=compiled,
        manifest=manifest,
        plan=pre_execution.plan,
        defer_clone=defer_clone,
        connection_config=planned.connection_config,
    )
    if prephase_exit is not None:
        return prephase_exit
    tracked: DbtTrackedExecution = execute_dbt_with_state_tracking(
        request=request,
        invocation=invocation,
        compiled=compiled,
        manifest=manifest,
        graph=resolution.graph,
        plan=pre_execution.plan,
        identities=identities,
        merged_dbt_argv=merged_dbt_argv,
        connection_config=planned.connection_config,
    )
    write_dbt_execution_summary(request=request, invocation=invocation, tracked=tracked)
    outcome: DbtExecutionOutcome = build_dbt_execution_outcome(
        plan=pre_execution.plan,
        graph=resolution.graph,
        node_results=tracked.execution.node_results,
    )
    if tracked.execution.returncode != 0 and not outcome.blocking_unique_ids:
        return tracked.execution.returncode
    if pre_execution.plan.sqlbuild_skip_reason is not None:
        write_sqlbuild_skip_notice(
            request=request,
            invocation=invocation,
            skip_reason_message="No SQLBuild work selected.",
            current_message=None,
        )
        return finalize_dbt_interop_exit(
            request=request,
            compiled=compiled,
            plan=pre_execution.plan,
            connection_config=planned.connection_config,
            dbt_returncode=tracked.execution.returncode,
            missing_relation_blocked_models=pre_execution.missing_relation_blocked_models,
        )
    replan: DbtSqlbuildReplanResult = resolve_sqlbuild_execution_plan_output(
        request=request,
        invocation=invocation,
        compiled=compiled,
        manifest=manifest,
        graph=resolution.graph,
        pre_execution=pre_execution,
        outcome=outcome,
        defer_clone=defer_clone,
        merged_dbt_argv=merged_dbt_argv,
    )
    if replan.plan_output is None:
        return finalize_dbt_interop_exit(
            request=request,
            compiled=compiled,
            plan=pre_execution.plan,
            connection_config=planned.connection_config,
            dbt_returncode=tracked.execution.returncode,
            missing_relation_blocked_models=replan.missing_relation_blocked_models,
        )
    if not plan_has_executable_work(replan.plan_output):
        write_sqlbuild_skip_notice(
            request=request,
            invocation=invocation,
            skip_reason_message=None,
            current_message="Skipping SQLBuild: selected models are already current.",
        )
        return finalize_dbt_interop_exit(
            request=request,
            compiled=compiled,
            plan=pre_execution.plan,
            connection_config=planned.connection_config,
            dbt_returncode=tracked.execution.returncode,
            missing_relation_blocked_models=replan.missing_relation_blocked_models,
        )
    sqlbuild_exit_code: int = run_dbt_sqlbuild_work(
        request=request,
        invocation=invocation,
        compiled=compiled,
        plan_output=replan.plan_output,
        connection_config=planned.connection_config,
    )
    if sqlbuild_exit_code != 0:
        return sqlbuild_exit_code
    return finalize_dbt_interop_exit(
        request=request,
        compiled=compiled,
        plan=pre_execution.plan,
        connection_config=planned.connection_config,
        dbt_returncode=tracked.execution.returncode,
        missing_relation_blocked_models=replan.missing_relation_blocked_models,
        always_append_freshness=True,
    )
