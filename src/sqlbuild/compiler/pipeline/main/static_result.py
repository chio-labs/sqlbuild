"""Public focused-command result assembly entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.pipeline.models import CompilePipelineResult, StaticCommandContext
from sqlbuild.compiler.planner.models import PlanOutput


def build_static_pipeline_result(
    *, context: StaticCommandContext, plan_output: PlanOutput
) -> CompilePipelineResult:
    """Wrap a focused command projection in the established pipeline envelope."""

    return CompilePipelineResult(
        project=context.project,
        plan_output=plan_output,
        compile_seconds=context.compile_seconds,
        planning_seconds=0.0,
    )
