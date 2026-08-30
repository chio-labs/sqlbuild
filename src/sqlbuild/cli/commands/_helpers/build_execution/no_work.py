"""No-work build completion boundary."""

from datetime import UTC, datetime

from sqlbuild.cli.commands._helpers.build_execution.outputs import write_no_work_build_json
from sqlbuild.cli.commands._helpers.build_execution.run_context import (
    write_build_run_context,
)
from sqlbuild.cli.commands._helpers.cost.collection import finalize_build_cost
from sqlbuild.cli.commands.models import (
    BuildCommandRequest,
    BuildCostFinalization,
    BuildInvocation,
    BuildRunContext,
)
from sqlbuild.compiler.pipeline.main.plan_work import plan_has_executable_work
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.cost.models import CostRunRecord


def finalize_no_work_build_if_needed(
    *,
    request: BuildCommandRequest,
    invocation: BuildInvocation,
    pipeline_result: CompilePipelineResult,
) -> bool:
    """Persist and emit a completed zero-cost record when the plan has no work."""

    if plan_has_executable_work(
        plan=pipeline_result.plan_output,
        python_plan_entries=pipeline_result.python_plan_entries,
    ):
        return False
    if request.verbose or request.debug:
        effective_concurrency: int = (
            request.concurrency
            if request.concurrency is not None
            else pipeline_result.project.settings.concurrency
        )
        write_build_run_context(
            stream=invocation.progress_stream,
            context=BuildRunContext(
                command="sqb build",
                project=pipeline_result.project,
                plan=pipeline_result.plan_output,
                discovered_inputs=invocation.discovered_inputs,
                python_plan_entries=pipeline_result.python_plan_entries,
                connection_config=invocation.connection_config,
                concurrency=effective_concurrency,
                full_refresh=request.full_refresh,
                selector_files=request.selector_files,
            ),
            use_color=invocation.use_color,
        )
    completed_at: datetime = datetime.now(UTC)
    cost_record: CostRunRecord | None = finalize_build_cost(
        BuildCostFinalization(
            project_dir=invocation.effective_project_dir,
            adapter_name=invocation.adapter_name,
            adapter=invocation.adapter,
            connection_config=invocation.connection_config,
            target_name=pipeline_result.project.effective_target_name,
            target_database=pipeline_result.project.effective_target_database,
            run_id=pipeline_result.project.run_id,
            build_status="success",
            started_at=completed_at,
            completed_at=completed_at,
            config=invocation.discovered_inputs.project_config.cost,
            output_stream=invocation.progress_stream,
            use_color=invocation.use_color,
            collect=False,
            had_executable_work=False,
        )
    )
    write_no_work_build_json(
        request=request,
        pipeline_result=pipeline_result,
        cost_record=cost_record,
    )
    return True
