"""CLI audit command entry point."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_project_connection_config
from sqlbuild.cli.commands.main.shared.helpers.connection_progress import ConnectionProgressReporter
from sqlbuild.cli.commands.main.shared.helpers.execution_json import (
    format_audit_execution_json,
    write_execution_json_output,
)
from sqlbuild.cli.commands.main.shared.helpers.external_refs import (
    resolve_external_sql_reference_resolver,
)
from sqlbuild.cli.commands.main.shared.helpers.nested_progress import NestedCommandProgressCallbacks
from sqlbuild.cli.commands.main.shared.helpers.planning_progress import PlanningProgressReporter
from sqlbuild.cli.commands.main.shared.helpers.progress import write_execution_header
from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.pipeline.main.run import run_audit_pipeline
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.helpers.colors import supports_color
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def run_audit(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    defer_to: str | None = None,
    no_color: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    cli_vars: dict[str, object] | None = None,
    json_output: bool = False,
    json_output_path: Path | None = None,
) -> int:
    """Execute the audit command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    adapter: BaseAdapter = resolve_adapter(
        resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        project_dir=effective_project_dir,
    )
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
        cli_vars=cli_vars,
    )
    use_color: bool = not no_color and supports_color()
    progress_stream: TextIO = sys.stderr if json_output else sys.stdout
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        stream=progress_stream,
        use_color=use_color,
    )
    planning_progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    progress_stream.write("\n")
    write_execution_header(
        stream=progress_stream,
        command="sqb audit",
        target=None,
        concurrency=1,
        use_color=use_color,
    )
    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        defer_to=defer_to,
        select=select,
        exclude=exclude,
        connection_config=connection_config,
        cli_vars=cli_vars,
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=connection_progress.on_connection_complete,
        on_connection_error=connection_progress.on_connection_error,
        on_progress=planning_progress.on_progress,
        external_sql_reference_resolver=resolve_external_sql_reference_resolver(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
        ),
    )

    audit_count: int = len(pipeline_result.plan_output.audit_entries)
    model_count: int = len(
        {
            e.attached_target_name
            for e in pipeline_result.plan_output.audit_entries
            if e.attached_target_name
        }
    )
    header: str = f"Audit ({audit_count} selected, {model_count} models)"
    style: CliStyle = CliStyle(use_color=use_color)
    styled_header: str = style.success_strong(header)
    progress: NestedCommandProgressCallbacks = NestedCommandProgressCallbacks(
        total=audit_count,
        label="audit",
        stream=progress_stream,
        use_color=use_color,
    )
    progress_stream.write(f"\n{styled_header}\n\n")
    progress_stream.flush()
    execution_connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        stream=progress_stream,
        use_color=use_color,
    )

    on_complete: Callable[[AuditExecutionResult], None] = _build_on_complete(progress=progress)
    results: tuple[AuditExecutionResult, ...] = run_audit_pipeline(
        plan=pipeline_result.plan_output,
        connection_config=connection_config,
        adapter=adapter,
        on_connection_start=execution_connection_progress.on_connection_start,
        on_connection_complete=execution_connection_progress.on_connection_complete,
        on_connection_error=execution_connection_progress.on_connection_error,
        on_audit_start=lambda entry: progress.on_item_start(
            group_name=entry.attached_target_name or "(unattached)",
            item_name=_audit_display_name_from_entry(entry),
        ),
        on_audit_complete=on_complete,
    )

    pass_count: int = sum(1 for r in results if r.outcome == AuditOutcome.PASS)
    warn_count: int = sum(1 for r in results if r.outcome == AuditOutcome.WARN)
    fail_count: int = sum(1 for r in results if r.outcome == AuditOutcome.ERROR)
    progress_stream.write(
        f"\nPASS={pass_count}  WARN={warn_count}  FAIL={fail_count}  TOTAL={len(results)}\n"
    )
    progress_stream.flush()
    write_execution_json_output(
        payload=format_audit_execution_json(results=results),
        json_output=json_output,
        json_output_path=json_output_path,
    )

    return 0 if fail_count == 0 else 1


def _build_on_complete(
    *, progress: NestedCommandProgressCallbacks
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
        )

    return _on_complete


def _audit_display_name_from_entry(entry: AuditPlanEntry) -> str:
    if entry.attached_column_name is not None:
        return f"{entry.name} ({entry.attached_column_name})"
    return entry.name
