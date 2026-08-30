"""Successful direct-build completion phase."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from sqlbuild.cli.commands._helpers.build_execution.outputs import (
    resolve_build_exit_code,
    write_build_completion_output,
    write_build_runtime_targets,
)
from sqlbuild.cli.commands._helpers.build_execution.phase_timings import (
    write_build_phase_timings,
)
from sqlbuild.cli.commands._helpers.cost.collection import finalize_build_cost, render_build_cost
from sqlbuild.cli.commands.models import (
    BuildCommandRequest,
    BuildCostFinalization,
    BuildExecutionPreparation,
    BuildInvocation,
    BuildPhaseTimings,
    BuildRunOutcome,
)
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.cost.models import CostRunRecord
from sqlbuild.diagnostics.classes.build_phase_timing_tracker import BuildPhaseTimingTracker
from sqlbuild.executor.python_nodes.models import PythonCheckExecutionResult


def complete_direct_build(
    *,
    request: BuildCommandRequest,
    invocation: BuildInvocation,
    pipeline_result: CompilePipelineResult,
    preparation: BuildExecutionPreparation,
    outcome: BuildRunOutcome,
    check_results: tuple[PythonCheckExecutionResult, ...],
    build_started_at: datetime,
    command_started_at: float,
) -> int:
    """Persist and render a completed direct build."""

    build_completed_at: datetime = datetime.now(UTC)
    exit_code: int = resolve_build_exit_code(outcome=outcome, check_results=check_results)
    write_build_runtime_targets(
        invocation=invocation,
        pipeline_result=pipeline_result,
        outcome=outcome,
        check_results=check_results,
    )
    cost_started_at: float = time.monotonic()
    cost_record: CostRunRecord | None = finalize_build_cost(
        BuildCostFinalization(
            project_dir=invocation.effective_project_dir,
            adapter_name=invocation.adapter_name,
            adapter=invocation.adapter,
            connection_config=invocation.connection_config,
            target_name=pipeline_result.project.effective_target_name,
            target_database=pipeline_result.project.effective_target_database,
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
    cost_collection_seconds: float = time.monotonic() - cost_started_at
    timing_tracker: BuildPhaseTimingTracker | None = BuildPhaseTimingTracker.current()
    if timing_tracker is not None:
        timing_tracker.cost_collection_seconds = cost_collection_seconds
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
    if request.verbose or request.debug:
        write_build_phase_timings(
            stream=invocation.progress_stream,
            timings=BuildPhaseTimings(
                compile_seconds=pipeline_result.compile_seconds,
                planning_seconds=pipeline_result.planning_seconds,
                connection_preparation_seconds=(
                    outcome.result.timings.connection_preparation_seconds
                ),
                schema_preparation_seconds=outcome.result.timings.schema_preparation_seconds,
                execution_seconds=outcome.result.timings.execution_seconds,
                cost_collection_seconds=cost_collection_seconds,
                total_seconds=time.monotonic() - command_started_at,
            ),
            use_color=invocation.use_color,
        )
    return exit_code
