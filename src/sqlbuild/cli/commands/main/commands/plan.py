"""CLI plan command entry point."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.plan.invocation import resolve_plan_invocation
from sqlbuild.cli.commands._helpers.plan.models import PlanCommandRequest, PlanInvocation
from sqlbuild.cli.commands._helpers.plan.outputs import write_plan_command_output
from sqlbuild.cli.commands._helpers.plan.planning import compile_plan_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult


def run_plan(request: PlanCommandRequest) -> int:
    """Execute the plan command."""

    invocation: PlanInvocation = resolve_plan_invocation(request=request)
    if not request.json_output:
        invocation.progress_stream.write("\n")
        invocation.progress_stream.flush()
    pipeline_result: CompilePipelineResult = compile_plan_pipeline(
        request=request,
        invocation=invocation,
    )
    write_plan_command_output(
        request=request,
        invocation=invocation,
        pipeline_result=pipeline_result,
    )
    return 0
