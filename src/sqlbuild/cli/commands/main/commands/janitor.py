"""CLI janitor command entry point."""

from __future__ import annotations

from sqlbuild.cli.commands.helpers.janitor.compilation import compile_janitor_project
from sqlbuild.cli.commands.helpers.janitor.connections import (
    close_janitor_warehouse,
    connect_janitor_warehouse,
)
from sqlbuild.cli.commands.helpers.janitor.execution import execute_janitor_cleanup
from sqlbuild.cli.commands.helpers.janitor.invocation import (
    resolve_janitor_invocation,
    resolve_janitor_settings,
)
from sqlbuild.cli.commands.helpers.janitor.models import (
    JanitorCommandRequest,
    JanitorCompileContext,
    JanitorConnectionContext,
    JanitorInvocation,
    JanitorPlanningResult,
    JanitorRetentionInspection,
    JanitorSettings,
)
from sqlbuild.cli.commands.helpers.janitor.outputs import (
    confirm_janitor_plan,
    janitor_plan_has_work,
    write_janitor_cancelled,
    write_janitor_completion,
    write_janitor_disabled,
    write_janitor_plan,
)
from sqlbuild.cli.commands.helpers.janitor.planning import (
    build_janitor_execution_plan,
    inspect_janitor_retention,
)
from sqlbuild.executor.janitor.models import JanitorExecutionResult


def run_janitor(request: JanitorCommandRequest) -> int:
    """Execute the janitor command."""

    invocation: JanitorInvocation = resolve_janitor_invocation(request=request)
    if not invocation.discovered_inputs.project_config.janitor.enabled:
        write_janitor_disabled(invocation=invocation)
        return 0
    settings: JanitorSettings = resolve_janitor_settings(request=request, invocation=invocation)
    compile_context: JanitorCompileContext = compile_janitor_project(invocation=invocation)
    connection_context: JanitorConnectionContext = connect_janitor_warehouse(
        invocation=invocation,
        compile_context=compile_context,
    )
    try:
        inspection: JanitorRetentionInspection = inspect_janitor_retention(
            invocation=invocation,
            settings=settings,
            compile_context=compile_context,
        )
        planning_result: JanitorPlanningResult = build_janitor_execution_plan(
            invocation=invocation,
            settings=settings,
            compile_context=compile_context,
            connection_context=connection_context,
            inspection=inspection,
        )
        write_janitor_plan(invocation=invocation, planning_result=planning_result)
        if not janitor_plan_has_work(planning_result):
            return 0
        if not request.auto_approve and not confirm_janitor_plan(planning_result=planning_result):
            write_janitor_cancelled()
            return 1
        result: JanitorExecutionResult = execute_janitor_cleanup(
            invocation=invocation,
            compile_context=compile_context,
            connection_context=connection_context,
            inspection=inspection,
            planning_result=planning_result,
        )
        write_janitor_completion(invocation=invocation, result=result)
        return 0
    finally:
        _ = close_janitor_warehouse(
            compile_context=compile_context,
            connection_context=connection_context,
        )
