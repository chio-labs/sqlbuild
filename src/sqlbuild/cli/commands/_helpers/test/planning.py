"""Test command plan compilation phase."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.planning.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands.models import TestCommandRequest, TestInvocation
from sqlbuild.compiler.pipeline.main.static_command import compile_static_command_context
from sqlbuild.compiler.pipeline.main.static_result import build_static_pipeline_result
from sqlbuild.compiler.pipeline.models import (
    CompilePipelineOptions,
    CompilePipelineResult,
    StaticCommandContext,
)
from sqlbuild.compiler.planner.main.commands.sql_test import build_test_command_plan


def compile_test_plan(
    *,
    request: TestCommandRequest,
    invocation: TestInvocation,
) -> CompilePipelineResult:
    """Compile the test plan for the selected scope."""

    options: CompilePipelineOptions = CompilePipelineOptions(
        selected_target=request.selected_target,
        no_sql_validation=request.no_sql_validation,
        source_deferral_enabled=False,
        select=request.select,
        exclude=request.exclude,
        connection_config=invocation.connection_config,
        cli_vars=request.cli_vars,
        external_sql_reference_resolver=resolve_external_sql_reference_resolver(
            project_dir=invocation.effective_project_dir,
            discovered_inputs=invocation.discovered_inputs,
        ),
    )
    context: StaticCommandContext = compile_static_command_context(
        discovered_inputs=invocation.discovered_inputs,
        adapter=invocation.adapter,
        options=options,
        on_progress=invocation.planning_progress.on_progress,
    )
    return build_static_pipeline_result(
        context=context,
        plan_output=build_test_command_plan(
            project=context.project,
            adapter=invocation.adapter,
            scope=context.scope,
            relations=context.relations,
        ),
    )
