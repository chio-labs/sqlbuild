"""Test command execution phases."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.cli.commands._helpers.test.sql_progress import (
    build_test_expectation_rows,
    format_parameterized_test_label,
    resolve_test_name_width,
    test_outcome_status,
)
from sqlbuild.cli.commands.models import (
    TestExecutionPreparation,
    TestInvocation,
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
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import SqlTestPlanEntry
from sqlbuild.executor.pipeline.main.run import run_test_pipeline
from sqlbuild.executor.testing.main.resource_id import sql_test_resource_id
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.presentation.main.surface_header import format_surface_header


def prepare_test_execution(
    *,
    invocation: TestInvocation,
    pipeline_result: CompilePipelineResult,
) -> TestExecutionPreparation:
    """Prepare nested progress reporting and write the test section header."""

    test_count: int = len(pipeline_result.plan_output.test_entries)
    model_names: set[str] = set()
    for entry in pipeline_result.plan_output.test_entries:
        for step in entry.chain:
            model_names.add(step.model_name)
    model_count: int = len(model_names)
    style: CliStyle = CliStyle(use_color=invocation.use_color)
    styled_header: str = format_surface_header(
        style=style,
        title="Test ready",
        context=f"{test_count} selected, {model_count} models",
    )
    progress: NestedCommandProgressCallbacks = NestedCommandProgressCallbacks(
        total=test_count,
        label="test",
        stream=invocation.progress_stream,
        use_color=invocation.use_color,
        name_width=resolve_test_name_width(pipeline_result.plan_output.test_entries),
    )
    projector: NativeProgressProjector | None = current_native_progress_projector()
    if projector is not None:
        for entry in pipeline_result.plan_output.test_entries:
            projector.expect_resource_enrichment(resource_name=entry.name)
    invocation.progress_stream.write(f"\n{styled_header}\n\n")
    invocation.progress_stream.flush()
    execution_connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=invocation.adapter_name,
        stream=invocation.progress_stream,
        use_color=invocation.use_color,
    )
    preflight_progress: TransientStatusReporter = TransientStatusReporter(
        stream=invocation.progress_stream,
        use_color=invocation.use_color,
    )
    return TestExecutionPreparation(
        progress=progress,
        execution_connection_progress=execution_connection_progress,
        preflight_progress=preflight_progress,
    )


def execute_test_plan(
    *,
    invocation: TestInvocation,
    pipeline_result: CompilePipelineResult,
    preparation: TestExecutionPreparation,
) -> tuple[SqlTestExecutionResult, ...]:
    """Execute the test plan with nested progress reporting."""

    event_writer: ExecutionEventWriter = ExecutionEventWriter()
    on_complete: Callable[[SqlTestExecutionResult], None] = _build_on_complete(
        progress=preparation.progress,
        event_writer=event_writer,
        pipeline_result=pipeline_result,
    )
    try:
        return run_test_pipeline(
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
            on_progress=preparation.preflight_progress.report_preflight_progress,
            on_test_start=lambda entry: preparation.progress.on_item_start(
                group_name=_test_group_name_from_entry(entry),
                item_name=format_parameterized_test_label(
                    name=entry.name,
                    source_path=entry.source_path,
                    parameter_schema=entry.parameter_schema,
                    parameter_values=entry.parameter_values,
                ),
                canonical_resource_name=entry.name,
            ),
            on_test_complete=on_complete,
            run_id=pipeline_result.project.run_id,
        )
    finally:
        event_writer.close()


def _build_on_complete(
    *,
    progress: NestedCommandProgressCallbacks,
    event_writer: ExecutionEventWriter,
    pipeline_result: CompilePipelineResult,
) -> Callable[[SqlTestExecutionResult], None]:
    def _on_complete(result: SqlTestExecutionResult) -> None:
        model_name: str = ""
        if result.step_results:
            model_name = result.step_results[0].model_name
        group_name: str = model_name or "(unknown)"
        status_text: str = test_outcome_status(outcome=result.outcome)
        progress.on_item_complete(
            group_name=group_name,
            item_name=format_parameterized_test_label(
                name=result.test_name,
                source_path=result.source_path,
                parameter_schema=result.parameter_schema,
                parameter_values=result.parameter_values,
            ),
            status_text=status_text,
            child_rows=build_test_expectation_rows(result),
            error_code=result.error_code,
            error_help=result.error_help,
            error_message=result.error_message,
            canonical_resource_name=result.test_name,
            canonical_resource_id=sql_test_resource_id(
                test_name=result.test_name,
                source_path=result.source_path,
                block_index=result.block_index,
                case_name=result.case_name,
            ),
        )
        event_writer.write_build_result(
            result=result,
            plan=pipeline_result.plan_output,
            command="test",
        )

    return _on_complete


def _test_group_name_from_entry(entry: SqlTestPlanEntry) -> str:
    if entry.chain:
        return entry.chain[0].model_name
    return "(unknown)"
