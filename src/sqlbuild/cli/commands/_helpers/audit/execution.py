"""Audit command execution phases."""

from __future__ import annotations

from sqlbuild.cli.commands.models import (
    AuditCommandRequest,
    AuditExecutionPreparation,
    AuditInvocation,
)
from sqlbuild.cli.output.classes.execution_event_writer import ExecutionEventWriter
from sqlbuild.cli.progress.classes.audit_progress_reporter import AuditProgressReporter
from sqlbuild.cli.progress.classes.connection_progress_reporter import (
    ConnectionProgressReporter,
)
from sqlbuild.cli.progress.classes.native_progress_projector import (
    NativeProgressProjector,
    current_native_progress_projector,
)
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.cost.classes.cost_context import CostContext
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.pipeline.main.run import (
    AuditPipelineCallbacks,
    run_audit_pipeline_with_callbacks,
)
from sqlbuild.presentation.classes.cli_style import CliStyle


def prepare_audit_execution(
    *,
    request: AuditCommandRequest,
    invocation: AuditInvocation,
    pipeline_result: CompilePipelineResult,
) -> AuditExecutionPreparation:
    """Prepare nested progress reporting and write the audit section header."""

    audit_count: int = len(pipeline_result.plan_output.audit_entries)
    effective_concurrency: int = (
        request.concurrency
        if request.concurrency is not None
        else pipeline_result.project.settings.concurrency
    )
    worker_count: int = min(effective_concurrency, audit_count)
    progress: AuditProgressReporter = AuditProgressReporter(
        entries=pipeline_result.plan_output.audit_entries,
        worker_limit=worker_count,
        stream=invocation.progress_stream,
        use_color=invocation.use_color,
    )
    projector: NativeProgressProjector | None = current_native_progress_projector()
    if projector is not None:
        for entry in pipeline_result.plan_output.audit_entries:
            projector.expect_resource_enrichment(resource_name=entry.name)
    execution_connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=invocation.adapter_name,
        stream=invocation.progress_stream,
        use_color=invocation.use_color,
    )
    return AuditExecutionPreparation(
        progress=progress,
        execution_connection_progress=execution_connection_progress,
        effective_concurrency=effective_concurrency,
        worker_count=worker_count,
    )


def write_audit_plan_header(
    *, invocation: AuditInvocation, pipeline_result: CompilePipelineResult
) -> None:
    """Write the selected audit section after effective execution settings."""

    entries: tuple[AuditPlanEntry, ...] = pipeline_result.plan_output.audit_entries
    model_count: int = len(
        {entry.attached_target_name for entry in entries if entry.attached_target_name}
    )
    header: str = f"Audit ({len(entries)} selected, {model_count} models)"
    styled_header: str = CliStyle(use_color=invocation.use_color).success_strong(header)
    invocation.progress_stream.write(f"\n{styled_header}\n\n")
    invocation.progress_stream.flush()


def execute_audit_plan(
    *,
    invocation: AuditInvocation,
    pipeline_result: CompilePipelineResult,
    preparation: AuditExecutionPreparation,
) -> tuple[AuditExecutionResult, ...]:
    """Execute the audit plan with nested progress reporting."""

    event_writer: ExecutionEventWriter = ExecutionEventWriter()
    preparation.progress.set_result_callback(
        lambda result: event_writer.write_build_result(
            result=result,
            plan=pipeline_result.plan_output,
            command="audit",
        )
    )
    projector: NativeProgressProjector | None = current_native_progress_projector()
    if projector is not None:
        projector.configure_resources(
            ordinals={
                entry.name: index
                for index, entry in enumerate(pipeline_result.plan_output.audit_entries, start=1)
            },
            total=len(pipeline_result.plan_output.audit_entries),
        )
    try:
        with CostContext.scope(
            run_id=pipeline_result.project.run_id,
            resource_type="run",
            resource_name="audit",
            ledger_path=(
                invocation.effective_project_dir
                / "target"
                / "executions"
                / pipeline_result.project.run_id
                / "statements.jsonl"
            ),
            phase="audit",
        ):
            return run_audit_pipeline_with_callbacks(
                plan=pipeline_result.plan_output,
                connection_config=invocation.connection_config,
                adapter=invocation.adapter,
                max_concurrency=preparation.effective_concurrency,
                callbacks=AuditPipelineCallbacks(
                    on_connection_start=(
                        preparation.execution_connection_progress.on_connection_start
                    ),
                    on_connection_complete=(
                        lambda connection_count, elapsed_seconds: (
                            preparation.execution_connection_progress.on_connection_complete(
                                connection_count=connection_count,
                                elapsed_seconds=elapsed_seconds,
                            )
                        )
                    ),
                    on_connection_error=(
                        lambda connection_count, elapsed_seconds: (
                            preparation.execution_connection_progress.on_connection_error(
                                connection_count=connection_count,
                                elapsed_seconds=elapsed_seconds,
                            )
                        )
                    ),
                    on_audit_start=preparation.progress.on_item_start,
                    on_audit_physical_complete=(preparation.progress.on_item_physical_complete),
                    on_audit_complete=preparation.progress.on_item_complete,
                    on_audit_error=preparation.progress.on_item_error,
                ),
                run_id=pipeline_result.project.run_id,
            )
    finally:
        preparation.progress.close()
        event_writer.close()
