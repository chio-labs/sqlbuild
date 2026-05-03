"""Build execution with live terminal output."""

from __future__ import annotations

import sys
import time
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.constants import INCREMENTAL_ACTIONS
from sqlbuild.executor.build.helpers.color import (
    colorize_completion,
    colorize_status,
    supports_color,
)
from sqlbuild.executor.build.main import execute_build_plan
from sqlbuild.executor.build.models import BuildExecutionResult, SeedExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus, TablePromotionMode
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome


def run_build_with_output(
    *,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection: Any,
    promotion_mode: TablePromotionMode,
    run_id: str,
    fingerprint_schema: str | None = None,
    run_audits: bool = True,
    run_tests: bool = True,
    fail_fast: bool = False,
    target: str | None = None,
    concurrency: int = 1,
    no_color: bool = False,
    plan_text: str | None = None,
) -> BuildExecutionResult:
    """Execute a build plan with live progress output to stdout."""

    use_color: bool = not no_color and supports_color()
    is_tty: bool = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

    if plan_text is not None:
        sys.stdout.write(plan_text + "\n\n")
        sys.stdout.flush()

    model_entry_map: dict[str, ModelPlanEntry] = {entry.name: entry for entry in plan.model_entries}
    test_results_by_model: dict[str, SqlTestExecutionResult] = {}
    total: int = len(plan.model_entries) + len(plan.seed_entries)
    counter: list[int] = [0]

    _print_header(target=target, concurrency=concurrency)

    def _on_node_start(name: str, materialization_type: str) -> None:
        if is_tty:
            ctr: str = f"{counter[0] + 1}/{total}".rjust(len(str(total)) * 2 + 1)
            display_type: str = _materialization_type_display(materialization_type)
            status: str = colorize_status("...", use_color=use_color)
            line: str = f"  {ctr}  {display_type:<6} {name:<40} {status}"
            sys.stdout.write(f"\r{line}")
            sys.stdout.flush()

    def _on_node_complete(node_result: object) -> None:
        if isinstance(node_result, SqlTestExecutionResult):
            step: object
            for step in node_result.step_results:
                if hasattr(step, "model_name"):
                    test_results_by_model[step.model_name] = node_result
            return

        if is_tty:
            sys.stdout.write("\r\033[K")

        counter[0] += 1
        ctr: str = f"{counter[0]}/{total}".rjust(len(str(total)) * 2 + 1)

        if isinstance(node_result, SeedExecutionResult):
            status: str = colorize_status(
                _execution_status_display(node_result.status), use_color=use_color
            )
            duration: str = _format_duration(node_result.duration_ms)
            sys.stdout.write(
                f"  {ctr}  seed   {node_result.seed_name:<40} {status:<6} {duration}\n"
            )
            sys.stdout.flush()
            return

        if isinstance(node_result, ModelExecutionResult):
            plan_entry: ModelPlanEntry | None = model_entry_map.get(node_result.model_name)
            display_type: str = _materialization_type_display(
                plan_entry.materialization_type if plan_entry else MaterializationType.TABLE
            )
            annotation: str = _resolve_annotation(plan_entry)

            name_display: str = node_result.model_name
            if annotation:
                name_display = f"{node_result.model_name}  ({annotation})"

            status = colorize_status(
                _execution_status_display(node_result.status), use_color=use_color
            )
            duration = _format_duration(node_result.duration_ms)
            detail: str = ""
            if (
                node_result.status == ExecutionStatus.FAILED
                and node_result.failed_phase is not None
            ):
                detail = f"  {node_result.failed_phase}"
            elif node_result.status == ExecutionStatus.SKIPPED:
                duration = ""

            sys.stdout.write(
                f"  {ctr}  {display_type:<6} {name_display:<40} {status:<6} {duration}{detail}\n"
            )

            test_result: SqlTestExecutionResult | None = test_results_by_model.get(
                node_result.model_name
            )
            if test_result is not None:
                test_status: str = colorize_status(
                    _test_outcome_display(test_result.outcome), use_color=use_color
                )
                sys.stdout.write(f"{'':>10}  test   {test_result.test_name:<40} {test_status}\n")

            audit: AuditExecutionResult
            for audit in node_result.audit_results:
                audit_status: str = colorize_status(
                    _audit_outcome_display(audit.outcome), use_color=use_color
                )
                audit_name: str = audit.audit_name
                if audit.attached_column_name is not None:
                    audit_name = f"{audit.audit_name} ({audit.attached_column_name})"
                audit_detail: str = ""
                if audit.outcome != AuditOutcome.PASS and audit.row_count > 0:
                    row_label: str = "row" if audit.row_count == 1 else "rows"
                    audit_detail = f"  {audit.row_count} {row_label}"
                sys.stdout.write(
                    f"{'':>10}  audit  {audit_name:<40} {audit_status}{audit_detail}\n"
                )

            sys.stdout.flush()

    start: float = time.monotonic()
    result: BuildExecutionResult = execute_build_plan(
        plan=plan,
        adapter=adapter,
        connections=(connection,),
        scheduler_connection=connection,
        promotion_mode=promotion_mode,
        run_id=run_id,
        fingerprint_schema=fingerprint_schema,
        run_audits=run_audits,
        run_tests=run_tests,
        fail_fast=fail_fast,
        on_node_start=_on_node_start,
        on_node_complete=_on_node_complete,
    )
    elapsed: float = time.monotonic() - start

    _print_footer(result=result, elapsed=elapsed, use_color=use_color)

    return result


def _print_header(*, target: str | None, concurrency: int) -> None:
    parts: list[str] = ["sqb build"]
    context_parts: list[str] = []
    if target is not None:
        context_parts.append(f"target: {target}")
    context_parts.append(f"concurrency: {concurrency}")
    if context_parts:
        parts.append(f"  ({', '.join(context_parts)})")
    sys.stdout.write("".join(parts) + "\n\n")
    sys.stdout.flush()


def _print_footer(
    *,
    result: BuildExecutionResult,
    elapsed: float,
    use_color: bool,
) -> None:
    sys.stdout.write("\n")

    warning_count: int = result.warning_count
    if result.status == BuildStatus.FAILED:
        msg: str = colorize_completion("Completed with errors.", use_color=use_color)
    elif warning_count > 0:
        msg = colorize_completion("Completed with warnings.", use_color=use_color)
    else:
        msg = colorize_completion("Completed successfully.", use_color=use_color)
    sys.stdout.write(msg + "\n")

    pass_count: int = 0
    warn_count: int = 0
    fail_count: int = 0
    skip_count: int = 0

    model_result: ModelExecutionResult
    for model_result in result.model_results:
        if model_result.status == ExecutionStatus.SUCCESS:
            pass_count += 1
        elif model_result.status == ExecutionStatus.FAILED:
            fail_count += 1
        elif model_result.status == ExecutionStatus.SKIPPED:
            skip_count += 1
        audit_r: AuditExecutionResult
        for audit_r in model_result.audit_results:
            if audit_r.outcome == AuditOutcome.PASS:
                pass_count += 1
            elif audit_r.outcome == AuditOutcome.WARN:
                warn_count += 1
            elif audit_r.outcome == AuditOutcome.ERROR:
                fail_count += 1

    seed_result: SeedExecutionResult
    for seed_result in result.seed_results:
        if seed_result.status == ExecutionStatus.SUCCESS:
            pass_count += 1
        elif seed_result.status == ExecutionStatus.FAILED:
            fail_count += 1
        elif seed_result.status == ExecutionStatus.SKIPPED:
            skip_count += 1

    test_r: SqlTestExecutionResult
    for test_r in result.test_results:
        if test_r.outcome == SqlTestOutcome.PASS:
            pass_count += 1
        else:
            fail_count += 1

    total_count: int = pass_count + warn_count + fail_count + skip_count
    elapsed_str: str = f"{elapsed:.2f}s"
    sys.stdout.write(
        f"PASS={pass_count}  WARN={warn_count}  FAIL={fail_count}  "
        f"SKIP={skip_count}  TOTAL={total_count}  ({elapsed_str})\n"
    )

    _print_failure_details(result)
    _print_warning_details(result)
    sys.stdout.flush()


def _print_failure_details(result: BuildExecutionResult) -> None:
    has_failures: bool = False
    model_result: ModelExecutionResult
    for model_result in result.model_results:
        if model_result.status != ExecutionStatus.FAILED:
            continue
        if not has_failures:
            sys.stdout.write("\nFailures:\n\n")
            has_failures = True
        phase_str: str = f"  ({model_result.failed_phase})" if model_result.failed_phase else ""
        sys.stdout.write(f"  {model_result.model_name}{phase_str}\n")
        if model_result.error_message is not None:
            sys.stdout.write(f"    {model_result.error_message}\n")
        if model_result.staging_relation is not None:
            sys.stdout.write(f"    staging retained as {model_result.staging_relation}\n")
        sys.stdout.write("\n")

    test_r: SqlTestExecutionResult
    for test_r in result.test_results:
        if test_r.outcome == SqlTestOutcome.PASS:
            continue
        if not has_failures:
            sys.stdout.write("\nFailures:\n\n")
            has_failures = True
        sys.stdout.write(f"  {test_r.test_name}  (test)\n")
        if test_r.error_message is not None:
            sys.stdout.write(f"    {test_r.error_message}\n")
        sys.stdout.write("\n")


def _print_warning_details(result: BuildExecutionResult) -> None:
    has_warnings: bool = False
    model_result: ModelExecutionResult
    for model_result in result.model_results:
        model_warnings: list[str] = []
        audit_r: AuditExecutionResult
        for audit_r in model_result.audit_results:
            if audit_r.outcome == AuditOutcome.WARN:
                name: str = audit_r.audit_name
                if audit_r.attached_column_name:
                    name = f"{audit_r.audit_name} ({audit_r.attached_column_name})"
                row_label: str = "row" if audit_r.row_count == 1 else "rows"
                model_warnings.append(f"    audit {name} returned {audit_r.row_count} {row_label}")
        warning_msg: str
        for warning_msg in model_result.warning_messages:
            model_warnings.append(f"    {warning_msg}")
        if model_warnings:
            if not has_warnings:
                sys.stdout.write("\nWarnings:\n\n")
                has_warnings = True
            sys.stdout.write(f"  {model_result.model_name}\n")
            line: str
            for line in model_warnings:
                sys.stdout.write(line + "\n")
            sys.stdout.write("\n")


def _format_duration(duration_ms: int | None) -> str:
    if duration_ms is None:
        return ""
    seconds: float = duration_ms / 1000.0
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes: int = int(seconds // 60)
    remaining: float = seconds - minutes * 60
    return f"{minutes}m{remaining:.1f}s"


def _execution_status_display(status: ExecutionStatus) -> str:
    if status == ExecutionStatus.SUCCESS:
        return "OK"
    if status == ExecutionStatus.FAILED:
        return "FAIL"
    if status == ExecutionStatus.SKIPPED:
        return "SKIP"
    return str(status)


def _audit_outcome_display(outcome: AuditOutcome) -> str:
    if outcome == AuditOutcome.PASS:
        return "PASS"
    if outcome == AuditOutcome.WARN:
        return "WARN"
    if outcome == AuditOutcome.ERROR:
        return "FAIL"
    return str(outcome)


def _test_outcome_display(outcome: SqlTestOutcome) -> str:
    if outcome == SqlTestOutcome.PASS:
        return "PASS"
    return "FAIL"


def _materialization_type_display(materialization_type: str) -> str:
    if materialization_type == MaterializationType.VIEW:
        return "view"
    if materialization_type == MaterializationType.SEED:
        return "seed"
    return "table"


def _resolve_annotation(plan_entry: ModelPlanEntry | None) -> str:
    if plan_entry is None:
        return ""
    if plan_entry.action not in INCREMENTAL_ACTIONS:
        return ""
    parts: list[str] = []
    if plan_entry.incremental_strategy:
        parts.append(plan_entry.incremental_strategy)
    return ", ".join(parts)
