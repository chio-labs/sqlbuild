"""Janitor command warehouse cleanup execution phase."""

from __future__ import annotations

from sqlbuild.cli.commands.models import (
    JanitorCompileContext,
    JanitorConnectionContext,
    JanitorPlanningResult,
)
from sqlbuild.executor.janitor.main.execute import execute_janitor_plan
from sqlbuild.executor.janitor.models import JanitorExecutionResult


def execute_janitor_cleanup(
    *,
    compile_context: JanitorCompileContext,
    connection_context: JanitorConnectionContext,
    planning_result: JanitorPlanningResult,
) -> JanitorExecutionResult:
    """Execute the warehouse cleanup plan."""

    return execute_janitor_plan(
        plan=planning_result.plan,
        adapter=compile_context.adapter,
        connection=connection_context.connection,
    )
