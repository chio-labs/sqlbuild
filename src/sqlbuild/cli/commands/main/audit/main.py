"""CLI audit command entry point."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.colors import colorize_status, supports_color
from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.discovery.main import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.pipeline.main import run_audit_pipeline


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
    adapter: BaseAdapter = resolve_adapter(discovered_inputs.project_config.adapter)
    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        defer_to=defer_to,
        select=select,
        exclude=exclude,
    )

    use_color: bool = not no_color and supports_color()
    sys.stdout.write("sqb audit\n\n")
    sys.stdout.flush()

    on_complete: Callable[[AuditExecutionResult], None] = _build_on_complete(use_color=use_color)
    results: tuple[AuditExecutionResult, ...] = run_audit_pipeline(
        plan=pipeline_result.plan_output,
        connection_config=dict(discovered_inputs.project_config.connection),
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
    def _on_complete(result: AuditExecutionResult) -> None:
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
        sys.stdout.write(f"  {audit_name:<50} {status}{detail}\n")
        sys.stdout.flush()

    return _on_complete
