"""Audit command execution phases."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.cli.commands.models import (
    AuditExecutionPreparation,
    AuditInvocation,
)
from sqlbuild.cli.output.classes.execution_event_writer import ExecutionEventWriter
from sqlbuild.cli.progress.classes.connection_progress_reporter import (
    ConnectionProgressReporter,
)
from sqlbuild.cli.progress.classes.native_progress_projector import (
    NativeProgressProjector,
    current_native_progress_projector,
)
from sqlbuild.cli.progress.classes.nested_command_progress_callbacks import (
    NestedCommandProgressCallbacks,
)
from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.executor.auditing.main.resource_id import audit_resource_id
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.pipeline.main.run import run_audit_pipeline
from sqlbuild.presentation.classes.cli_style import CliStyle


def prepare_audit_execution(
    *,
    invocation: AuditInvocation,
    pipeline_result: CompilePipelineResult,
) -> AuditExecutionPreparation:
    """Prepare nested progress reporting and write the audit section header."""

    audit_count: int = len(pipeline_result.plan_output.audit_entries)
    model_count: int = len(
        {
            e.attached_target_name
            for e in pipeline_result.plan_output.audit_entries
            if e.attached_target_name
        }
    )
    header: str = f"Audit ({audit_count} selected, {model_count} models)"
    style: CliStyle = CliStyle(use_color=invocation.use_color)
    styled_header: str = style.success_strong(header)
    progress: NestedCommandProgressCallbacks = NestedCommandProgressCallbacks(
        total=audit_count,
        label="audit",
        stream=invocation.progress_stream,
        use_color=invocation.use_color,
    )
    projector: NativeProgressProjector | None = current_native_progress_projector()
    if projector is not None:
        for entry in pipeline_result.plan_output.audit_entries:
            projector.expect_resource_enrichment(resource_name=entry.name)
    invocation.progress_stream.write(f"\n{styled_header}\n\n")
    invocation.progress_stream.flush()
    execution_connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=invocation.adapter_name,
        stream=invocation.progress_stream,
        use_color=invocation.use_color,
    )
    return AuditExecutionPreparation(
        progress=progress,
        execution_connection_progress=execution_connection_progress,
    )


def execute_audit_plan(
    *,
    invocation: AuditInvocation,
    pipeline_result: CompilePipelineResult,
    preparation: AuditExecutionPreparation,
) -> tuple[AuditExecutionResult, ...]:
    """Execute the audit plan with nested progress reporting."""

    event_writer: ExecutionEventWriter = ExecutionEventWriter()
    on_complete: Callable[[AuditExecutionResult], None] = _build_on_complete(
        progress=preparation.progress,
        event_writer=event_writer,
        pipeline_result=pipeline_result,
    )
    try:
        return run_audit_pipeline(
            plan=pipeline_result.plan_output,
            connection_config=invocation.connection_config,
            adapter=invocation.adapter,
            on_connection_start=preparation.execution_connection_progress.on_connection_start,
            on_connection_complete=lambda connection_count, elapsed_seconds: (
                preparation.execution_connection_progress.on_connection_complete(
                    connection_count=connection_count, elapsed_seconds=elapsed_seconds
                )
            ),
            on_connection_error=lambda connection_count, elapsed_seconds: (
                preparation.execution_connection_progress.on_connection_error(
                    connection_count=connection_count, elapsed_seconds=elapsed_seconds
                )
            ),
            on_audit_start=lambda entry: preparation.progress.on_item_start(
                group_name=entry.attached_target_name or "(unattached)",
                item_name=_audit_display_name_from_entry(entry),
            ),
            on_audit_complete=on_complete,
            run_id=pipeline_result.project.run_id,
        )
    finally:
        event_writer.close()


def _build_on_complete(
    *,
    progress: NestedCommandProgressCallbacks,
    event_writer: ExecutionEventWriter,
    pipeline_result: CompilePipelineResult,
) -> Callable[[AuditExecutionResult], None]:
    def _on_complete(result: AuditExecutionResult) -> None:
        group_name: str = result.attached_target_name or "(unattached)"
        status_text: str
        if result.outcome == AuditOutcome.PASS:
            status_text = "PASS"
        elif result.outcome == AuditOutcome.WARN:
            status_text = "WARN"
        else:
            status_text = "FAIL"
        audit_name: str = result.audit_name
        if result.attached_column_name is not None:
            audit_name = f"{result.audit_name} ({result.attached_column_name})"
        detail: str = ""
        if result.outcome != AuditOutcome.PASS and result.row_count > 0:
            row_label: str = "row" if result.row_count == 1 else "rows"
            detail = f"  {result.row_count} {row_label}"
        progress.on_item_complete(
            group_name=group_name,
            item_name=audit_name,
            status_text=status_text,
            detail=detail,
            canonical_resource_id=audit_resource_id(
                audit_name=result.audit_name,
                attachment_kind=result.attachment_kind,
                attached_target_kind=result.attached_target_kind,
                attached_target_name=result.attached_target_name,
                attached_column_name=result.attached_column_name,
            ),
        )
        event_writer.write_build_result(
            result=result,
            plan=pipeline_result.plan_output,
            command="audit",
        )

    return _on_complete


def _audit_display_name_from_entry(entry: AuditPlanEntry) -> str:
    if entry.attached_column_name is not None:
        return f"{entry.name} ({entry.attached_column_name})"
    return entry.name
