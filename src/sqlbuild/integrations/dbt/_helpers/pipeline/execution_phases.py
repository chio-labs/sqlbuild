"""Ordinary execution phases for dbt interop."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.cli.commands.main.dbt.dbt_sqlbuild_work import execute_dbt_sqlbuild_work
from sqlbuild.cli.commands.main.execution.connection_progress import (
    build_connection_progress_reporter,
)
from sqlbuild.cli.commands.models import DbtSqlbuildWorkContext
from sqlbuild.cli.progress.classes.connection_progress_reporter import ConnectionProgressReporter
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.integrations.dbt._helpers.pipeline.execute import (
    execute_dbt_commands,
    render_dbt_execution_summary_footer,
)
from sqlbuild.integrations.dbt._helpers.pipeline.plan_output import build_sqlbuild_plan_output
from sqlbuild.integrations.dbt.main.pipeline.render_plan import render_dbt_interop_plan
from sqlbuild.integrations.dbt.main.profile._resolve_connection_config import (
    resolve_connection_config,
)
from sqlbuild.integrations.dbt.main.runtime._report_progress import report_progress
from sqlbuild.integrations.dbt.models import (
    DbtCommandExecutionResult,
    DbtInteropCompiledProject,
    DbtInteropExecutionRequest,
    DbtInteropInvocation,
    DbtInteropPlan,
    DbtManifestIndex,
    DbtPlanEnvironment,
    DbtSqlbuildPlanRequest,
)
from sqlbuild.presentation.models import DisplayOptions
from sqlbuild.runtime.contracts.models import ConnectionHooks


def resolve_dbt_connection_config(
    *,
    request: DbtInteropExecutionRequest,
    invocation: DbtInteropInvocation,
    compiled: DbtInteropCompiledProject,
) -> dict[str, object]:
    """Resolve the connection used only by selected SQLBuild work."""

    return resolve_connection_config(
        raw_config=build_effective_connection_config(
            discovered_inputs=invocation.discovered_inputs
        ),
        project_dir=request.project_dir,
        adapter_name=compiled.adapter_name,
        discovered_inputs=invocation.discovered_inputs,
    )


def write_dbt_execution_plan_text(
    *,
    request: DbtInteropExecutionRequest,
    invocation: DbtInteropInvocation,
    plan: DbtInteropPlan,
    merged_dbt_argv: tuple[str, ...] | None,
) -> None:
    """Render the selected work without model-state classifications."""

    if request.json_output:
        return
    display_plan: DbtInteropPlan = (
        replace(plan, dbt_command_argv=merged_dbt_argv, supplemental_dbt_command_argvs=())
        if merged_dbt_argv is not None
        else plan
    )
    rendered_plan: str = render_dbt_interop_plan(
        plan=display_plan,
        json_output=False,
        use_color=request.use_color,
        display_options=DisplayOptions(max_entries_per_section=None if request.verbose else 10),
    )
    invocation.output_stream.write(rendered_plan + "\n\n")
    invocation.output_stream.flush()


def execute_dbt_without_state_tracking(
    *,
    request: DbtInteropExecutionRequest,
    invocation: DbtInteropInvocation,
    merged_dbt_argv: tuple[str, ...] | None,
) -> DbtCommandExecutionResult:
    """Execute ordinary dbt events without SQLBuild state reads or writes."""

    return execute_dbt_commands(
        runner=invocation.runner,
        options=invocation.dbt_options,
        merged_argv=merged_dbt_argv,
        progress_stream=invocation.output_stream,
        stdout_stream=invocation.dbt_output_stream,
        use_color=request.use_color,
        skip_message="Skipping dbt: no dbt work selected.",
        on_progress=request.on_progress,
    )


def write_dbt_execution_summary(
    *,
    request: DbtInteropExecutionRequest,
    invocation: DbtInteropInvocation,
    execution: DbtCommandExecutionResult,
) -> None:
    """Write the ordinary dbt event summary footer."""

    summary_footer: str | None = render_dbt_execution_summary_footer(
        node_results=execution.node_results,
        use_color=request.use_color,
    )
    if summary_footer is not None:
        invocation.output_stream.write("\n" + summary_footer + "\n")
        invocation.output_stream.flush()


def resolve_sqlbuild_execution_plan_output(
    *,
    request: DbtInteropExecutionRequest,
    invocation: DbtInteropInvocation,
    compiled: DbtInteropCompiledProject,
    manifest: DbtManifestIndex,
    plan: DbtInteropPlan,
    failed_sqlbuild_model_names: tuple[str, ...],
) -> PlanOutput | None:
    """Plan selected SQLBuild work after dbt using actual dbt failures as blockers."""

    if plan.sqlbuild_skip_reason is not None:
        return None
    selected_model_names: tuple[str, ...] = plan.selection.sqlbuild_model_names
    if not selected_model_names:
        return None
    invocation.output_stream.write("\n")
    invocation.output_stream.flush()
    connection_progress: ConnectionProgressReporter = build_connection_progress_reporter(
        adapter_name=compiled.adapter_name,
        stream=invocation.output_stream,
        blank_line_after_complete=True,
        use_color=request.use_color,
    )
    return build_sqlbuild_plan_output(
        environment=DbtPlanEnvironment(
            project_dir=request.project_dir,
            discovered_inputs=invocation.discovered_inputs,
            project=compiled.project,
            adapter=compiled.adapter,
            adapter_name=compiled.adapter_name,
        ),
        request=DbtSqlbuildPlanRequest(
            selected_model_names=selected_model_names,
            sqlbuild_args=invocation.effective_sqlbuild_args,
            external_blocked_model_names=failed_sqlbuild_model_names,
        ),
        hooks=ConnectionHooks(
            on_connection_start=connection_progress.on_connection_start,
            on_connection_complete=lambda connection_count, *, elapsed_seconds: (
                connection_progress.on_connection_complete(
                    connection_count=connection_count,
                    elapsed_seconds=elapsed_seconds,
                )
            ),
            on_connection_error=lambda connection_count, *, elapsed_seconds: (
                connection_progress.on_connection_error(
                    connection_count=connection_count,
                    elapsed_seconds=elapsed_seconds,
                )
            ),
        ),
    )


def run_dbt_sqlbuild_work(
    *,
    request: DbtInteropExecutionRequest,
    invocation: DbtInteropInvocation,
    compiled: DbtInteropCompiledProject,
    plan_output: PlanOutput,
    connection_config: dict[str, object],
) -> int:
    """Execute the SQLBuild portion of the interop plan and return its exit code."""

    return execute_dbt_sqlbuild_work(
        context=DbtSqlbuildWorkContext(
            plan_output=plan_output,
            connection_config=connection_config,
            adapter=compiled.adapter,
            adapter_name=compiled.adapter_name,
            output_stream=invocation.output_stream,
            use_color=request.use_color,
        ),
        command=request.command,
        project=compiled.project,
        project_dir=request.project_dir,
        fail_fast=request.fail_fast,
        verbose=request.verbose,
    )


def write_sqlbuild_skip_notice(
    *, request: DbtInteropExecutionRequest, invocation: DbtInteropInvocation, message: str
) -> None:
    """Write the SQLBuild skip transition."""

    invocation.output_stream.write("\n")
    invocation.output_stream.flush()
    report_progress(on_progress=request.on_progress, message=message)
