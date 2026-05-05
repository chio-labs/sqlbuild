"""CLI audit command entry point."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_project_connection_config
from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.pipeline.main.run import run_audit_pipeline
from sqlbuild.shared.helpers.colors import bold, colorize_status, green_bold, supports_color
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def run_audit(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    defer_to: str | None = None,
    no_color: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
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
    )
    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        defer_to=defer_to,
        select=select,
        exclude=exclude,
        connection_config=connection_config,
    )

    use_color: bool = not no_color and supports_color()
    audit_count: int = len(pipeline_result.plan_output.audit_entries)
    model_count: int = len(
        {
            e.attached_target_name
            for e in pipeline_result.plan_output.audit_entries
            if e.attached_target_name
        }
    )
    header: str = f"Audit ({audit_count} selected, {model_count} models)"
    styled_header: str = green_bold(header) if use_color else header
    sys.stdout.write(f"\n{styled_header}\n")
    sys.stdout.flush()

    on_complete: Callable[[AuditExecutionResult], None] = _build_on_complete(use_color=use_color)
    results: tuple[AuditExecutionResult, ...] = run_audit_pipeline(
        plan=pipeline_result.plan_output,
        connection_config=connection_config,
        adapter=adapter,
        on_audit_complete=on_complete,
    )

    pass_count: int = sum(1 for r in results if r.outcome == AuditOutcome.PASS)
    warn_count: int = sum(1 for r in results if r.outcome == AuditOutcome.WARN)
    fail_count: int = sum(1 for r in results if r.outcome == AuditOutcome.ERROR)
    sys.stdout.write(
        f"\nPASS={pass_count}  WARN={warn_count}  FAIL={fail_count}  TOTAL={len(results)}\n"
    )
    sys.stdout.flush()

    return 0 if fail_count == 0 else 1


def _build_on_complete(*, use_color: bool) -> Callable[[AuditExecutionResult], None]:
    current_group: list[str] = [""]

    def _on_complete(result: AuditExecutionResult) -> None:
        group_name: str = result.attached_target_name or "(unattached)"
        if group_name != current_group[0]:
            current_group[0] = group_name
            group_header: str = bold(group_name) if use_color else group_name
            sys.stdout.write(f"\n{group_header}\n")

        status_text: str
        if result.outcome == AuditOutcome.PASS:
            status_text = "PASS"
        elif result.outcome == AuditOutcome.WARN:
            status_text = "WARN"
        else:
            status_text = "FAIL"
        status: str = colorize_status(status_text, use_color=use_color)
        audit_name: str = result.audit_name
        if result.attached_column_name is not None:
            audit_name = f"{result.audit_name} ({result.attached_column_name})"
        detail: str = ""
        if result.outcome != AuditOutcome.PASS and result.row_count > 0:
            row_label: str = "row" if result.row_count == 1 else "rows"
            detail = f"  {result.row_count} {row_label}"
        sys.stdout.write(f"    {'audit':<10}{audit_name:<40} {status}{detail}\n")
        sys.stdout.flush()

    return _on_complete
