"""Exceptional direct-build cost finalization."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlbuild.cli.commands._helpers.cost.collection import finalize_build_cost
from sqlbuild.cli.commands.models import BuildCostFinalization, BuildInvocation
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.cost.types import CostStatus


def finalize_exceptional_direct_cost(
    *,
    invocation: BuildInvocation,
    pipeline_result: CompilePipelineResult,
    build_started_at: datetime,
    error: BaseException,
) -> None:
    """Persist failed/interrupted cost state without masking the active error."""

    interrupted: bool = isinstance(error, KeyboardInterrupt)
    try:
        _ = finalize_build_cost(
            BuildCostFinalization(
                project_dir=invocation.effective_project_dir,
                adapter_name=invocation.adapter_name,
                adapter=invocation.adapter,
                connection_config=invocation.connection_config,
                target_name=pipeline_result.project.effective_target_name,
                target_database=pipeline_result.project.effective_target_database,
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
