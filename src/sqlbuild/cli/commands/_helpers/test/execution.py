"""Test command execution phases."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.cli.commands._helpers.test.models import (
    TestExecutionPreparation,
    TestInvocation,
)
from sqlbuild.cli.commands._helpers.test.sql_progress import (
    build_test_expectation_rows,
    resolve_test_name_width,
)
from sqlbuild.cli.progress.classes.connection_progress_reporter import (
    ConnectionProgressReporter,
)
from sqlbuild.cli.progress.classes.nested_command_progress_callbacks import (
    NestedCommandProgressCallbacks,
)
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import SqlTestPlanEntry
from sqlbuild.executor.pipeline.main.run import run_test_pipeline
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter


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
    header: str = f"Test ({test_count} selected, {model_count} models)"
    style: CliStyle = CliStyle(use_color=invocation.use_color)
    styled_header: str = style.success_strong(header)
    progress: NestedCommandProgressCallbacks = NestedCommandProgressCallbacks(
        total=test_count,
        label="test",
        stream=invocation.progress_stream,
        use_color=invocation.use_color,
        name_width=resolve_test_name_width(pipeline_result.plan_output.test_entries),
    )
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

    on_complete: Callable[[SqlTestExecutionResult], None] = _build_on_complete(
        progress=preparation.progress
    )
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
            item_name=entry.name,
        ),
        on_test_complete=on_complete,
    )


def _build_on_complete(
    *, progress: NestedCommandProgressCallbacks
) -> Callable[[SqlTestExecutionResult], None]:
    def _on_complete(result: SqlTestExecutionResult) -> None:
        model_name: str = ""
        if result.step_results:
            model_name = result.step_results[0].model_name
        group_name: str = model_name or "(unknown)"
        status_text: str = "PASS" if result.outcome == SqlTestOutcome.PASS else "FAIL"
        progress.on_item_complete(
            group_name=group_name,
            item_name=result.test_name,
            status_text=status_text,
            child_rows=build_test_expectation_rows(result),
            error_code=result.error_code,
            error_help=result.error_help,
            error_message=result.error_message,
        )

    return _on_complete


def _test_group_name_from_entry(entry: SqlTestPlanEntry) -> str:
    if entry.chain:
        return entry.chain[0].model_name
    return "(unknown)"
