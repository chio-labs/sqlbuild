"""Clone command planning phase."""

from __future__ import annotations

import time

from sqlbuild.cli.commands._helpers.planning.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import (
    CloneCommandRequest,
    CloneConnectionContext,
    CloneExecutionPreparation,
    CloneInvocation,
)
from sqlbuild.cli.progress.classes.planning_progress_reporter import PlanningProgressReporter
from sqlbuild.compiler.pipeline.main.clone import run_clone_pipeline
from sqlbuild.compiler.pipeline.models import ClonePipelineConnection, ClonePipelineResult
from sqlbuild.compiler.planner.models import (
    CloneSourcePlanEntry,
    FunctionPlanEntry,
    ModelPlanEntry,
    SeedPlanEntry,
)
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle


def prepare_clone_execution(
    *,
    request: CloneCommandRequest,
    invocation: CloneInvocation,
    connection_context: CloneConnectionContext,
) -> CloneExecutionPreparation:
    """Prepare the direct clone plan."""

    progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=invocation.progress_stream,
        use_color=invocation.use_color,
    )
    planning_start: float = time.monotonic()
    with OperationLifecycle(operation_kind="project", operation_name="project_compile"):
        progress.on_progress("Preparing clone plan...")
        pipeline_result: ClonePipelineResult = run_clone_pipeline(
            discovered_inputs=invocation.discovered_inputs,
            adapter=invocation.adapter,
            origin_target_name=request.origin_target_name,
            destination_target_name=invocation.destination_target_name,
            no_sql_validation=request.no_sql_validation,
            select=request.select,
            exclude=request.exclude,
            cli_vars=request.cli_vars,
            destination_connection=ClonePipelineConnection(
                config=connection_context.destination_connection_config,
                handle=connection_context.destination_connection,
            ),
            external_sql_reference_resolver=resolve_external_sql_reference_resolver(
                project_dir=invocation.effective_project_dir,
                discovered_inputs=invocation.discovered_inputs,
            ),
        )
        progress.on_progress(f"Prepared clone plan. ({time.monotonic() - planning_start:.2f}s)")
    destination_model_entries: tuple[ModelPlanEntry, ...] = (
        pipeline_result.destination_model_entries
    )
    destination_seed_entries: tuple[SeedPlanEntry, ...] = pipeline_result.destination_seed_entries
    destination_source_entries: tuple[CloneSourcePlanEntry, ...] = (
        pipeline_result.destination_source_entries
    )
    destination_function_entries: tuple[FunctionPlanEntry, ...] = (
        pipeline_result.destination_function_entries
    )
    if (
        not destination_model_entries
        and not destination_seed_entries
        and not destination_source_entries
        and not destination_function_entries
    ):
        raise CliUserError("no cloneable resources found in the selected scope", code="C407")
    return CloneExecutionPreparation(pipeline_result=pipeline_result)
