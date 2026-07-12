"""SQLBuild work helpers for dbt interop commands."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands.helpers.build.progress import (
    BuildProgressCallbacks,
    format_build_footer,
)
from sqlbuild.cli.commands.helpers.dbt.models import DbtSqlbuildWorkContext
from sqlbuild.cli.commands.helpers.test.sql_progress import (
    build_test_expectation_rows,
    resolve_test_name_width,
)
from sqlbuild.cli.progress.classes.connection_progress_reporter import ConnectionProgressReporter
from sqlbuild.cli.progress.classes.nested_command_progress_callbacks import (
    NestedCommandProgressCallbacks,
)
from sqlbuild.cli.progress.main.execution_header import format_execution_header
from sqlbuild.cli.target_artifacts.main.write_runtime_target import write_runtime_target
from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.planner.models import (
    AuditPlanEntry,
    ChainStep,
    PlanOutput,
    SqlTestPlanEntry,
)
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.models import (
    BuildCallbacks,
    BuildExecutionResult,
    BuildRuntimeParams,
)
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.pipeline.main.run import (
    run_audit_pipeline,
    run_build_pipeline,
    run_test_pipeline,
)
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.integrations.dbt.types import DbtInteropCommand, DbtInteropSqlbuildTestAction
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.presentation.main.summary_footer import format_summary_footer


def execute_sqlbuild_build_work(
    *,
    context: DbtSqlbuildWorkContext,
    command: DbtInteropCommand,
    project: CompiledProject,
    project_dir: Path,
    fail_fast: bool,
    verbose: bool,
) -> int:
    plan_output: PlanOutput = context.plan_output
    connection_config: dict[str, object] = context.connection_config
    adapter: BaseAdapter = context.adapter
    adapter_name: str = context.adapter_name
    output_stream: TextIO = context.output_stream
    use_color: bool = context.use_color
    callbacks: BuildProgressCallbacks = BuildProgressCallbacks(
        plan=plan_output, use_color=use_color, verbose=verbose, debug=False
    )
    effective_concurrency: int = project.settings.concurrency
    display_command: str = (
        "sqb build --no-tests --no-audits"
        if command == DbtInteropCommand.RUN
        else f"sqb {command.value}"
    )
    header: str = format_execution_header(
        command=display_command, target=None, concurrency=effective_concurrency
    )
    style: CliStyle = CliStyle(use_color=use_color)
    execution_label: str = style.object_name("SQLBuild execution")
    header_detail: str = style.muted(header)
    output_stream.write(f"{execution_label}  {header_detail}\n\n")
    output_stream.flush()
    execution_connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=output_stream,
        blank_line_after_complete=True,
        use_color=use_color,
    )
    result: BuildExecutionResult = run_build_pipeline(
        plan=plan_output,
        connection_config=connection_config,
        adapter=adapter,
        settings=project.settings,
        runtime=BuildRuntimeParams(
            run_id=project.run_id,
            run_tests=command == DbtInteropCommand.BUILD,
            run_audits=command == DbtInteropCommand.BUILD,
            fail_fast=fail_fast,
            max_concurrency=effective_concurrency,
            use_color=use_color,
        ),
        callbacks=BuildCallbacks(
            on_node_start=lambda name, resource_kind: callbacks.on_node_start(
                name=name, resource_kind=resource_kind
            ),
            on_node_complete=callbacks.on_node_complete,
            on_sub_progress=callbacks.on_sub_progress,
            on_connection_start=execution_connection_progress.on_connection_start,
            on_connection_complete=lambda connection_count, elapsed_seconds: (
                execution_connection_progress.on_connection_complete(
                    connection_count=connection_count, elapsed_seconds=elapsed_seconds
                )
            ),
            on_connection_error=lambda connection_count, elapsed_seconds: (
                execution_connection_progress.on_connection_error(
                    connection_count=connection_count, elapsed_seconds=elapsed_seconds
                )
            ),
        ),
    )
    write_runtime_target(target_dir=project_dir / "target", plan_output=plan_output, result=result)
    footer: str = format_build_footer(result=result, elapsed=callbacks.elapsed, use_color=use_color)
    output_stream.write("\n" + footer + "\n")
    output_stream.flush()
    return 0 if result.status == BuildStatus.SUCCESS else 1


def execute_sqlbuild_test_work(
    *,
    context: DbtSqlbuildWorkContext,
    actions: tuple[DbtInteropSqlbuildTestAction, ...],
) -> int:
    plan_output: PlanOutput = context.plan_output
    connection_config: dict[str, object] = context.connection_config
    adapter: BaseAdapter = context.adapter
    adapter_name: str = context.adapter_name
    output_stream: TextIO = context.output_stream
    use_color: bool = context.use_color
    exit_code: int = 0
    action: DbtInteropSqlbuildTestAction
    for action in actions:
        if action == DbtInteropSqlbuildTestAction.TEST:
            if not plan_output.test_entries:
                continue
            exit_code = max(
                exit_code,
                _execute_sqlbuild_tests(
                    plan_output=plan_output,
                    connection_config=connection_config,
                    adapter=adapter,
                    adapter_name=adapter_name,
                    output_stream=output_stream,
                    use_color=use_color,
                ),
            )
        elif action == DbtInteropSqlbuildTestAction.AUDIT:
            if not plan_output.audit_entries:
                continue
            exit_code = max(
                exit_code,
                _execute_sqlbuild_audits(
                    plan_output=plan_output,
                    connection_config=connection_config,
                    adapter=adapter,
                    adapter_name=adapter_name,
                    output_stream=output_stream,
                    use_color=use_color,
                ),
            )
    return exit_code


def _execute_sqlbuild_tests(
    *,
    plan_output: PlanOutput,
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    adapter_name: str,
    output_stream: TextIO,
    use_color: bool,
) -> int:
    header: str = format_execution_header(command="sqb test", target=None, concurrency=1)
    style: CliStyle = CliStyle(use_color=use_color)
    execution_label: str = style.object_name("SQLBuild execution")
    header_detail: str = style.muted(header)
    output_stream.write(f"{execution_label}  {header_detail}\n\n")
    test_count: int = len(plan_output.test_entries)
    output_stream.write(f"{style.success_strong(f'Test ({test_count} selected)')}\n\n")
    output_stream.flush()
    target_by_test_name: dict[str, str] = {
        entry.name: _test_group_name_from_entry(entry) for entry in plan_output.test_entries
    }
    progress: NestedCommandProgressCallbacks = NestedCommandProgressCallbacks(
        total=test_count,
        label="test",
        stream=output_stream,
        use_color=use_color,
        name_width=resolve_test_name_width(plan_output.test_entries),
    )
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=output_stream,
        blank_line_after_complete=True,
        use_color=use_color,
    )
    preflight_progress: TransientStatusReporter = TransientStatusReporter(
        stream=output_stream,
        use_color=use_color,
    )
    results: tuple[SqlTestExecutionResult, ...] = run_test_pipeline(
        plan=plan_output,
        connection_config=connection_config,
        adapter=adapter,
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=lambda connection_count, elapsed_seconds: (
            connection_progress.on_connection_complete(
                connection_count=connection_count, elapsed_seconds=elapsed_seconds
            )
        ),
        on_connection_error=lambda connection_count, elapsed_seconds: (
            connection_progress.on_connection_error(
                connection_count=connection_count, elapsed_seconds=elapsed_seconds
            )
        ),
        on_progress=preflight_progress.report_preflight_progress,
        on_test_start=lambda entry: progress.on_item_start(
            group_name=_test_group_name_from_entry(entry),
            item_name=entry.name,
        ),
        on_test_complete=_build_test_on_complete(
            progress=progress, target_by_test_name=target_by_test_name
        ),
    )
    pass_count: int = sum(1 for r in results if r.outcome == SqlTestOutcome.PASS)
    fail_count: int = len(results) - pass_count
    output_stream.write(
        "\n"
        + format_summary_footer(
            counts=(
                ("PASS", pass_count),
                ("FAIL", fail_count),
                ("TOTAL", len(results)),
            ),
            use_color=use_color,
        )
        + "\n\n"
    )
    output_stream.flush()
    return 0 if fail_count == 0 else 1


def _execute_sqlbuild_audits(
    *,
    plan_output: PlanOutput,
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    adapter_name: str,
    output_stream: TextIO,
    use_color: bool,
) -> int:
    header: str = format_execution_header(command="sqb audit", target=None, concurrency=1)
    style: CliStyle = CliStyle(use_color=use_color)
    execution_label: str = style.object_name("SQLBuild execution")
    header_detail: str = style.muted(header)
    output_stream.write(f"{execution_label}  {header_detail}\n\n")
    audit_count: int = len(plan_output.audit_entries)
    model_count: int = len(
        {
            entry.attached_target_name
            for entry in plan_output.audit_entries
            if entry.attached_target_name
        }
    )
    output_stream.write(
        f"{style.success_strong(f'Audit ({audit_count} selected, {model_count} models)')}\n\n"
    )
    output_stream.flush()
    progress: NestedCommandProgressCallbacks = NestedCommandProgressCallbacks(
        total=audit_count,
        label="audit",
        stream=output_stream,
        use_color=use_color,
    )
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=output_stream,
        blank_line_after_complete=True,
        use_color=use_color,
    )
    results: tuple[AuditExecutionResult, ...] = run_audit_pipeline(
        plan=plan_output,
        connection_config=connection_config,
        adapter=adapter,
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=lambda connection_count, elapsed_seconds: (
            connection_progress.on_connection_complete(
                connection_count=connection_count, elapsed_seconds=elapsed_seconds
            )
        ),
        on_connection_error=lambda connection_count, elapsed_seconds: (
            connection_progress.on_connection_error(
                connection_count=connection_count, elapsed_seconds=elapsed_seconds
            )
        ),
        on_audit_start=lambda entry: progress.on_item_start(
            group_name=entry.attached_target_name or "(unattached)",
            item_name=_audit_display_name_from_entry(entry),
        ),
        on_audit_complete=_build_audit_on_complete(progress=progress),
    )
    pass_count: int = sum(1 for r in results if r.outcome == AuditOutcome.PASS)
    warn_count: int = sum(1 for r in results if r.outcome == AuditOutcome.WARN)
    fail_count: int = sum(1 for r in results if r.outcome == AuditOutcome.ERROR)
    output_stream.write(
        "\n"
        + format_summary_footer(
            counts=(
                ("PASS", pass_count),
                ("WARN", warn_count),
                ("FAIL", fail_count),
                ("TOTAL", len(results)),
            ),
            use_color=use_color,
        )
        + "\n\n"
    )
    output_stream.flush()
    return 0 if fail_count == 0 else 1


def _build_test_on_complete(
    *,
    progress: NestedCommandProgressCallbacks,
    target_by_test_name: dict[str, str],
) -> Callable[[SqlTestExecutionResult], None]:
    def _on_complete(result: SqlTestExecutionResult) -> None:
        group_name: str = target_by_test_name.get(result.test_name, "")
        if not group_name and result.step_results:
            group_name = result.step_results[0].model_name
        status_text: str = "PASS" if result.outcome == SqlTestOutcome.PASS else "FAIL"
        progress.on_item_complete(
            group_name=group_name or "(unknown)",
            item_name=result.test_name,
            status_text=status_text,
            child_rows=build_test_expectation_rows(result),
            error_code=result.error_code,
            error_help=result.error_help,
            error_message=result.error_message,
        )

    return _on_complete


def _build_audit_on_complete(
    *, progress: NestedCommandProgressCallbacks
) -> Callable[[AuditExecutionResult], None]:
    def _on_complete(result: AuditExecutionResult) -> None:
        status_text: str
        if result.outcome == AuditOutcome.PASS:
            status_text = "PASS"
        elif result.outcome == AuditOutcome.WARN:
            status_text = "WARN"
        else:
            status_text = "FAIL"
        detail: str = ""
        if result.outcome != AuditOutcome.PASS and result.row_count > 0:
            row_label: str = "row" if result.row_count == 1 else "rows"
            detail = f"  {result.row_count} {row_label}"
        progress.on_item_complete(
            group_name=result.attached_target_name or "(unattached)",
            item_name=_audit_display_name_from_result(result),
            status_text=status_text,
            detail=detail,
        )

    return _on_complete


def _test_group_name_from_entry(entry: SqlTestPlanEntry) -> str:
    if not entry.chain:
        return "(unknown)"
    expected_steps: tuple[ChainStep, ...] = tuple(
        step for step in entry.chain if step.expected_cte_sql is not None
    )
    if expected_steps:
        return expected_steps[-1].model_name
    return entry.chain[-1].model_name


def _audit_display_name_from_entry(entry: AuditPlanEntry) -> str:
    if entry.attached_column_name is not None:
        return f"{entry.name} ({entry.attached_column_name})"
    return entry.name


def _audit_display_name_from_result(result: AuditExecutionResult) -> str:
    if result.attached_column_name is not None:
        return f"{result.audit_name} ({result.attached_column_name})"
    return result.audit_name
