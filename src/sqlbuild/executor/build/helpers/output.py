"""Build execution output formatting."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.adapter.shared.models import LifeCycleEvent
from sqlbuild.adapter.shared.types import LifeCycleEventKind
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.constants import INCREMENTAL_ACTIONS
from sqlbuild.executor.build.helpers.color import colorize_completion, colorize_status
from sqlbuild.executor.build.models import BuildExecutionResult, SeedExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome


@dataclass(frozen=True)
class _AuditDisplayEntry:
    """Aggregated audit result for display."""

    label: str
    display_name: str
    outcome: AuditOutcome
    total_row_count: int
    batch_pass: int
    batch_total: int
    executed_sql: str | None = None


def format_build_output(
    *,
    result: BuildExecutionResult,
    plan: PlanOutput,
    target: str | None = None,
    concurrency: int = 1,
    elapsed_seconds: float = 0.0,
    use_color: bool = False,
    verbose: bool = False,
) -> str:
    """Format the complete build execution output."""

    model_entry_map: dict[str, ModelPlanEntry] = {entry.name: entry for entry in plan.model_entries}
    test_results_by_model: dict[str, SqlTestExecutionResult] = _build_test_results_by_model(
        result.test_results
    )
    lines: list[str] = []
    lines.append(_format_header(target=target, concurrency=concurrency))
    lines.append("")

    counter: int = 0
    total: int = _count_top_level_nodes(result)

    seed_result: SeedExecutionResult
    for seed_result in result.seed_results:
        counter += 1
        lines.append(
            _format_seed_line(
                seed_result=seed_result,
                counter=counter,
                total=total,
                use_color=use_color,
            )
        )

    model_result: ModelExecutionResult
    for model_result in result.model_results:
        counter += 1
        plan_entry: ModelPlanEntry | None = model_entry_map.get(model_result.model_name)
        resource_type: str = _resolve_resource_type(plan_entry)
        annotation: str = _resolve_annotation(plan_entry)

        lines.append(
            _format_model_line(
                model_result=model_result,
                resource_type=resource_type,
                annotation=annotation,
                counter=counter,
                total=total,
                use_color=use_color,
            )
        )

        if verbose:
            event: LifeCycleEvent
            for event in _resolve_verbose_events(
                model_result=model_result,
                plan_entry=plan_entry,
            ):
                if event.kind == LifeCycleEventKind.SQL:
                    lines.extend(_format_sql_block(event.content))
                elif event.kind == LifeCycleEventKind.LOG:
                    lines.extend(_format_log_block(event.content))

        test_result: SqlTestExecutionResult | None = test_results_by_model.get(
            model_result.model_name
        )
        if test_result is not None:
            lines.append(
                _format_sub_line(
                    sub_type="test",
                    name=test_result.test_name,
                    status=_test_outcome_to_status(test_result.outcome),
                    use_color=use_color,
                )
            )

        audit_entries: list[_AuditDisplayEntry] = _aggregate_audit_results(
            model_result.audit_results
        )
        audit_entry: _AuditDisplayEntry
        for audit_entry in audit_entries:
            lines.append(_format_audit_sub_line(audit_entry, use_color=use_color))
            if verbose and audit_entry.executed_sql is not None:
                lines.extend(_format_sql_block(audit_entry.executed_sql))

    lines.append("")
    lines.append(
        _format_completion_message(result.status, result.warning_count, use_color=use_color)
    )
    lines.append(_format_summary_counts(result=result, elapsed_seconds=elapsed_seconds))

    failure_lines: list[str] = _format_failure_details(result)
    if failure_lines:
        lines.append("")
        lines.extend(failure_lines)

    warning_lines: list[str] = _format_warning_details(result)
    if warning_lines:
        lines.append("")
        lines.extend(warning_lines)

    return "\n".join(lines)


def _format_header(*, target: str | None, concurrency: int) -> str:
    parts: list[str] = ["sqb build"]
    context_parts: list[str] = []
    if target is not None:
        context_parts.append(f"target: {target}")
    context_parts.append(f"concurrency: {concurrency}")
    if context_parts:
        parts.append(f"  ({', '.join(context_parts)})")
    return "".join(parts)


def _format_seed_line(
    *,
    seed_result: SeedExecutionResult,
    counter: int,
    total: int,
    use_color: bool,
) -> str:
    counter_str: str = f"{counter}/{total}".rjust(len(str(total)) * 2 + 1)
    status: str = _execution_status_to_display(seed_result.status)
    colored_status: str = colorize_status(status, use_color=use_color)
    duration: str = _format_duration(seed_result.duration_ms)
    return f"  {counter_str}  seed   {seed_result.seed_name:<40} {colored_status:<6} {duration}"


def _format_model_line(
    *,
    model_result: ModelExecutionResult,
    resource_type: str,
    annotation: str,
    counter: int,
    total: int,
    use_color: bool,
) -> str:
    counter_str: str = f"{counter}/{total}".rjust(len(str(total)) * 2 + 1)
    name_and_annotation: str = model_result.model_name
    if annotation:
        name_and_annotation = f"{model_result.model_name}  ({annotation})"

    status: str = _execution_status_to_display(model_result.status)
    colored_status: str = colorize_status(status, use_color=use_color)
    duration: str = _format_duration(model_result.duration_ms)
    detail: str = ""
    if model_result.status == ExecutionStatus.FAILED and model_result.failed_phase is not None:
        detail = f"  {model_result.failed_phase}"
    elif model_result.status == ExecutionStatus.SKIPPED:
        duration = ""
    line: str = (
        f"  {counter_str}  {resource_type:<6} {name_and_annotation:<40} "
        f"{colored_status:<6} {duration}{detail}"
    )
    return line


def _format_sql_block(sql: str) -> list[str]:
    """Format a SQL block with minimal indent for verbose output."""

    lines: list[str] = [""]
    sql_line: str
    for sql_line in _format_display_sql(sql).split("\n"):
        lines.append(f"    {sql_line}")
    lines.append("")
    return lines


def _format_display_sql(sql: str) -> str:
    stripped: str = sql.rstrip()
    if not stripped:
        return sql
    if stripped.endswith(";"):
        return stripped
    return f"{stripped};"


def _resolve_verbose_events(
    *, model_result: ModelExecutionResult, plan_entry: ModelPlanEntry | None
) -> tuple[LifeCycleEvent, ...]:
    if model_result.lifecycle_events:
        return model_result.lifecycle_events
    if plan_entry is not None:
        return (LifeCycleEvent(kind=LifeCycleEventKind.SQL, content=plan_entry.logical_ddl),)
    return ()


def _format_log_block(message: str) -> list[str]:
    """Format a log message with indent for verbose output."""

    return ["", f"    -- {message}", ""]


def _format_sub_line(*, sub_type: str, name: str, status: str, use_color: bool) -> str:
    colored_status: str = colorize_status(status, use_color=use_color)
    padding: str = " " * 10
    return f"{padding}  {sub_type:<6} {name:<40} {colored_status}"


def _format_audit_sub_line(entry: _AuditDisplayEntry, *, use_color: bool) -> str:
    status: str = _audit_outcome_to_display(entry.outcome)
    detail: str = ""
    if entry.outcome != AuditOutcome.PASS and entry.total_row_count > 0:
        row_label: str = "row" if entry.total_row_count == 1 else "rows"
        detail = f"  {entry.total_row_count} {row_label}"
    if entry.batch_total > 1:
        detail = f"  {entry.batch_pass}/{entry.batch_total}" + detail
    return _format_sub_line(
        sub_type=entry.label,
        name=entry.display_name,
        status=f"{status}{detail}",
        use_color=use_color,
    )


def _format_completion_message(status: BuildStatus, warning_count: int, *, use_color: bool) -> str:
    if status == BuildStatus.FAILED:
        return colorize_completion("Completed with errors.", use_color=use_color)
    if warning_count > 0:
        return colorize_completion("Completed with warnings.", use_color=use_color)
    return colorize_completion("Completed successfully.", use_color=use_color)


def _format_summary_counts(
    *,
    result: BuildExecutionResult,
    elapsed_seconds: float,
) -> str:
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
        audit_result: AuditExecutionResult
        for audit_result in model_result.audit_results:
            if audit_result.outcome == AuditOutcome.PASS:
                pass_count += 1
            elif audit_result.outcome == AuditOutcome.WARN:
                warn_count += 1
            elif audit_result.outcome == AuditOutcome.ERROR:
                fail_count += 1

    seed_result: SeedExecutionResult
    for seed_result in result.seed_results:
        if seed_result.status == ExecutionStatus.SUCCESS:
            pass_count += 1
        elif seed_result.status == ExecutionStatus.FAILED:
            fail_count += 1
        elif seed_result.status == ExecutionStatus.SKIPPED:
            skip_count += 1

    test_result: SqlTestExecutionResult
    for test_result in result.test_results:
        if test_result.outcome == SqlTestOutcome.PASS:
            pass_count += 1
        else:
            fail_count += 1

    end_audit: AuditExecutionResult
    for end_audit in result.end_audit_results:
        if end_audit.outcome == AuditOutcome.PASS:
            pass_count += 1
        elif end_audit.outcome == AuditOutcome.WARN:
            warn_count += 1
        elif end_audit.outcome == AuditOutcome.ERROR:
            fail_count += 1

    source_audit: AuditExecutionResult
    for source_audit in result.source_audit_results:
        if source_audit.outcome == AuditOutcome.PASS:
            pass_count += 1
        elif source_audit.outcome == AuditOutcome.WARN:
            warn_count += 1
        elif source_audit.outcome == AuditOutcome.ERROR:
            fail_count += 1

    total: int = pass_count + warn_count + fail_count + skip_count
    elapsed_str: str = f"{elapsed_seconds:.2f}s" if elapsed_seconds > 0 else ""
    time_part: str = f"  ({elapsed_str})" if elapsed_str else ""
    counts: str = (
        f"PASS={pass_count}  WARN={warn_count}  FAIL={fail_count}  "
        f"SKIP={skip_count}  TOTAL={total}{time_part}"
    )
    return counts


def _format_failure_details(result: BuildExecutionResult) -> list[str]:
    lines: list[str] = []
    has_failures: bool = False

    model_result: ModelExecutionResult
    for model_result in result.model_results:
        if model_result.status != ExecutionStatus.FAILED:
            continue
        if not has_failures:
            lines.append("Failures:")
            lines.append("")
            has_failures = True
        phase_str: str = f"  ({model_result.failed_phase})" if model_result.failed_phase else ""
        lines.append(f"  {model_result.model_name}{phase_str}")
        if model_result.error_message is not None:
            lines.append(f"    {model_result.error_message}")
        if model_result.staging_relation is not None:
            lines.append(f"    staging retained as {model_result.staging_relation}")
        lines.append("")

    test_result: SqlTestExecutionResult
    for test_result in result.test_results:
        if test_result.outcome == SqlTestOutcome.PASS:
            continue
        if not has_failures:
            lines.append("Failures:")
            lines.append("")
            has_failures = True
        lines.append(f"  {test_result.test_name}  (test)")
        if test_result.error_message is not None:
            lines.append(f"    {test_result.error_message}")
        lines.append("")

    return lines


def _format_warning_details(result: BuildExecutionResult) -> list[str]:
    lines: list[str] = []
    has_warnings: bool = False

    model_result: ModelExecutionResult
    for model_result in result.model_results:
        model_warnings: list[str] = []
        audit_result: AuditExecutionResult
        for audit_result in model_result.audit_results:
            if audit_result.outcome == AuditOutcome.WARN:
                name: str = audit_result.audit_name
                if audit_result.attached_column_name:
                    name = f"{audit_result.audit_name} ({audit_result.attached_column_name})"
                row_label: str = "row" if audit_result.row_count == 1 else "rows"
                model_warnings.append(
                    f"    audit {name} returned {audit_result.row_count} {row_label}"
                )
        warning_msg: str
        for warning_msg in model_result.warning_messages:
            model_warnings.append(f"    {warning_msg}")
        if model_warnings:
            if not has_warnings:
                lines.append("Warnings:")
                lines.append("")
                has_warnings = True
            lines.append(f"  {model_result.model_name}")
            lines.extend(model_warnings)
            lines.append("")

    return lines


def _count_top_level_nodes(result: BuildExecutionResult) -> int:
    return len(result.model_results) + len(result.seed_results)


def _build_test_results_by_model(
    test_results: tuple[SqlTestExecutionResult, ...],
) -> dict[str, SqlTestExecutionResult]:
    result_map: dict[str, SqlTestExecutionResult] = {}
    test_result: SqlTestExecutionResult
    for test_result in test_results:
        step: object
        for step in test_result.step_results:
            if hasattr(step, "model_name"):
                result_map[step.model_name] = test_result
    return result_map


def _resolve_resource_type(plan_entry: ModelPlanEntry | None) -> str:
    if plan_entry is None:
        return MaterializationType.TABLE
    if plan_entry.materialization_type == MaterializationType.VIEW:
        return MaterializationType.VIEW
    return MaterializationType.TABLE


def _resolve_annotation(plan_entry: ModelPlanEntry | None) -> str:
    if plan_entry is None:
        return ""
    if plan_entry.action not in INCREMENTAL_ACTIONS:
        return ""
    parts: list[str] = []
    if plan_entry.incremental_strategy:
        parts.append(plan_entry.incremental_strategy)
    return ", ".join(parts)


def _format_duration(duration_ms: int | None) -> str:
    if duration_ms is None:
        return ""
    seconds: float = duration_ms / 1000.0
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes: int = int(seconds // 60)
    remaining: float = seconds - minutes * 60
    return f"{minutes}m{remaining:.1f}s"


def _execution_status_to_display(status: ExecutionStatus) -> str:
    if status == ExecutionStatus.SUCCESS:
        return "OK"
    if status == ExecutionStatus.FAILED:
        return "FAIL"
    if status == ExecutionStatus.SKIPPED:
        return "SKIP"
    return str(status)


def _aggregate_audit_results(
    audit_results: tuple[AuditExecutionResult, ...],
) -> list[_AuditDisplayEntry]:
    """Aggregate per-batch delta audit results into single display entries."""

    has_delta: bool = any(a.run_scope_phase == AuditRunScope.DELTA_AND_FINAL for a in audit_results)

    groups: dict[tuple[str, str | None, str], list[AuditExecutionResult]] = {}
    audit: AuditExecutionResult
    for audit in audit_results:
        key: tuple[str, str | None, str] = (
            audit.audit_name,
            audit.attached_column_name,
            audit.run_scope_phase,
        )
        groups.setdefault(key, []).append(audit)

    entries: list[_AuditDisplayEntry] = []
    results: list[AuditExecutionResult]
    for (_name, _col, _phase), results in groups.items():
        display_name: str = _name
        if _col is not None:
            display_name = f"{_name} ({_col})"
        worst: AuditOutcome = _worst_audit_outcome(results)
        total_rows: int = sum(r.row_count for r in results)
        pass_count: int = sum(1 for r in results if r.outcome == AuditOutcome.PASS)
        label: str = _phase_label(_phase, has_delta_audits=has_delta)
        entries.append(
            _AuditDisplayEntry(
                label=label,
                display_name=display_name,
                outcome=worst,
                total_row_count=total_rows,
                batch_pass=pass_count,
                batch_total=len(results),
                executed_sql=results[0].executed_sql if results else None,
            )
        )

    return entries


def _worst_audit_outcome(results: list[AuditExecutionResult]) -> AuditOutcome:
    """Return the worst outcome from a list of audit results."""

    has_error: bool = any(r.outcome == AuditOutcome.ERROR for r in results)
    if has_error:
        return AuditOutcome.ERROR
    has_warn: bool = any(r.outcome == AuditOutcome.WARN for r in results)
    if has_warn:
        return AuditOutcome.WARN
    return AuditOutcome.PASS


def _phase_label(phase: str, *, has_delta_audits: bool) -> str:
    """Return the audit type label, annotated with phase when delta audits are present."""

    if not has_delta_audits:
        return "audit"
    if phase == AuditRunScope.DELTA_AND_FINAL:
        return "audit (d)"
    return "audit (f)"


def _audit_outcome_to_display(outcome: AuditOutcome) -> str:
    if outcome == AuditOutcome.PASS:
        return "PASS"
    if outcome == AuditOutcome.WARN:
        return "WARN"
    if outcome == AuditOutcome.ERROR:
        return "FAIL"
    return str(outcome)


def _test_outcome_to_status(outcome: SqlTestOutcome) -> str:
    if outcome == SqlTestOutcome.PASS:
        return "PASS"
    if outcome == SqlTestOutcome.FAIL:
        return "FAIL"
    if outcome == SqlTestOutcome.ERROR:
        return "FAIL"
    return str(outcome)
