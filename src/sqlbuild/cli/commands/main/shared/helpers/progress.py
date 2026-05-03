"""Build progress output callbacks and summary formatting."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass

from sqlbuild.cli.commands.main.shared.helpers.colors import (
    colorize_completion,
    colorize_status,
)
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.constants import INCREMENTAL_ACTIONS
from sqlbuild.executor.build.models import BuildExecutionResult, SeedExecutionResult
from sqlbuild.executor.build.types import BuildStatus, ExecutionStatus
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome

_TYPE_WIDTH: int = 10
_MAX_NAME_WIDTH: int = 60
_MIN_NAME_WIDTH: int = 20
_NAME_PADDING: int = 2


@dataclass(frozen=True)
class _AuditDisplayEntry:
    """Aggregated audit result for display."""

    label: str
    display_name: str
    outcome: AuditOutcome
    total_row_count: int
    batch_pass: int
    batch_total: int


class BuildProgressCallbacks:
    """Encapsulates live build progress output state and callbacks."""

    def __init__(
        self,
        *,
        plan: PlanOutput,
        use_color: bool,
    ) -> None:
        self._model_entry_map: dict[str, ModelPlanEntry] = {
            entry.name: entry for entry in plan.model_entries
        }
        self._test_results_by_model: dict[str, SqlTestExecutionResult] = {}
        self._total: int = len(plan.model_entries) + len(plan.seed_entries)
        self._counter: int = 0
        self._use_color: bool = use_color
        self._is_tty: bool = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
        self._start_time: float = time.monotonic()
        self._current_node_name: str = ""
        self._current_node_type: str = ""
        self._current_sub_message: str = ""

        ctr_width: int = len(str(self._total)) * 2 + 1
        self._prefix_width: int = 2 + ctr_width + 2

        max_name_len: int = 0
        entry: ModelPlanEntry
        for entry in plan.model_entries:
            annotation: str = _resolve_annotation(entry)
            display_name: str = entry.name
            if annotation:
                display_name = f"{entry.name}  ({annotation})"
            max_name_len = max(max_name_len, len(display_name))
        seed_entry: object
        for seed_entry in plan.seed_entries:
            max_name_len = max(max_name_len, len(getattr(seed_entry, "name", str(seed_entry))))
        self._name_width: int = max(
            min(max_name_len + _NAME_PADDING, _MAX_NAME_WIDTH), _MIN_NAME_WIDTH
        )

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._start_time

    def on_node_start(self, name: str, materialization_type: str) -> None:
        self._current_node_name = name
        self._current_node_type = materialization_type
        self._current_sub_message = ""
        if self._is_tty:
            self._write_spinner_line()

    def on_sub_progress(self, message: str) -> None:
        self._current_sub_message = message
        if self._is_tty:
            self._write_spinner_line()

    def _write_spinner_line(self) -> None:
        ctr: str = f"{self._counter + 1}/{self._total}".rjust(len(str(self._total)) * 2 + 1)
        display_type: str = _materialization_type_display(self._current_node_type)
        status: str = colorize_status("...", use_color=self._use_color)
        name_display: str = _truncate_name(self._current_node_name, self._name_width)
        if self._current_sub_message:
            name_display = _truncate_name(
                f"{self._current_node_name}  {self._current_sub_message}", self._name_width
            )
        nw: int = self._name_width
        line: str = f"  {ctr}  {display_type:<{_TYPE_WIDTH}}{name_display:<{nw}} {status}"
        sys.stdout.write(f"\r\033[K{line}")
        sys.stdout.flush()

    def on_node_complete(self, node_result: object) -> None:
        if isinstance(node_result, SqlTestExecutionResult):
            step: object
            for step in node_result.step_results:
                if hasattr(step, "model_name"):
                    self._test_results_by_model[step.model_name] = node_result
            return

        if self._is_tty:
            sys.stdout.write("\r\033[K")

        self._counter += 1
        ctr: str = f"{self._counter}/{self._total}".rjust(len(str(self._total)) * 2 + 1)

        if isinstance(node_result, SeedExecutionResult):
            status: str = colorize_status(
                _execution_status_display(node_result.status),
                use_color=self._use_color,
            )
            duration: str = _format_duration(node_result.duration_ms)
            seed_name: str = _truncate_name(node_result.seed_name, self._name_width)
            nw: int = self._name_width
            sys.stdout.write(
                f"  {ctr}  {'seed':<{_TYPE_WIDTH}}{seed_name:<{nw}} {status:<6} {duration}\n"
            )
            sys.stdout.flush()
            return

        if isinstance(node_result, ModelExecutionResult):
            self._write_model_result(ctr=ctr, model_result=node_result)

    def _write_model_result(self, *, ctr: str, model_result: ModelExecutionResult) -> None:
        plan_entry: ModelPlanEntry | None = self._model_entry_map.get(model_result.model_name)
        display_type: str = _materialization_type_display(
            plan_entry.materialization_type if plan_entry else MaterializationType.TABLE
        )
        annotation: str = _resolve_annotation(plan_entry)
        name_display: str = model_result.model_name
        if annotation:
            name_display = f"{model_result.model_name}  ({annotation})"
        name_display = _truncate_name(name_display, self._name_width)

        status: str = colorize_status(
            _execution_status_display(model_result.status),
            use_color=self._use_color,
        )
        duration: str = _format_duration(model_result.duration_ms)
        detail: str = ""
        if model_result.status == ExecutionStatus.FAILED and model_result.failed_phase is not None:
            detail = f"  {model_result.failed_phase}"
        elif model_result.status == ExecutionStatus.SKIPPED:
            duration = ""

        nw: int = self._name_width
        line: str = (
            f"  {ctr}  {display_type:<{_TYPE_WIDTH}}{name_display:<{nw}}"
            f" {status:<6} {duration}{detail}\n"
        )
        sys.stdout.write(line)

        pad: str = " " * self._prefix_width
        nw: int = self._name_width

        test_result: SqlTestExecutionResult | None = self._test_results_by_model.get(
            model_result.model_name
        )
        if test_result is not None:
            test_status: str = colorize_status(
                _test_outcome_display(test_result.outcome),
                use_color=self._use_color,
            )
            test_name: str = _truncate_name(test_result.test_name, nw)
            sys.stdout.write(f"{pad}{'test':<{_TYPE_WIDTH}}{test_name:<{nw}} {test_status}\n")

        display_audits: list[_AuditDisplayEntry] = _aggregate_audit_results(
            model_result.audit_results
        )

        entry: _AuditDisplayEntry
        for entry in display_audits:
            audit_status: str = colorize_status(
                _audit_outcome_display(entry.outcome), use_color=self._use_color
            )
            audit_name: str = _truncate_name(entry.display_name, nw)
            audit_detail: str = ""
            if entry.outcome != AuditOutcome.PASS and entry.total_row_count > 0:
                row_label: str = "row" if entry.total_row_count == 1 else "rows"
                audit_detail = f"  {entry.total_row_count} {row_label}"
            if entry.batch_total > 1:
                audit_detail = f"  {entry.batch_pass}/{entry.batch_total}" + audit_detail
            audit_line: str = (
                f"{pad}{entry.label:<{_TYPE_WIDTH}}{audit_name:<{nw}}"
                f" {audit_status}{audit_detail}\n"
            )
            sys.stdout.write(audit_line)

        sys.stdout.flush()


def format_build_header(*, command: str, target: str | None, concurrency: int) -> str:
    parts: list[str] = [command]
    context_parts: list[str] = []
    if target is not None:
        context_parts.append(f"target: {target}")
    context_parts.append(f"concurrency: {concurrency}")
    if context_parts:
        parts.append(f"  ({', '.join(context_parts)})")
    return "".join(parts)


def format_build_footer(
    *,
    result: BuildExecutionResult,
    elapsed: float,
    use_color: bool,
) -> str:
    lines: list[str] = []

    if result.status == BuildStatus.FAILED:
        lines.append(colorize_completion("Completed with errors.", use_color=use_color))
    elif result.warning_count > 0:
        lines.append(colorize_completion("Completed with warnings.", use_color=use_color))
    else:
        lines.append(colorize_completion("Completed successfully.", use_color=use_color))

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
    lines.append(
        f"PASS={pass_count}  WARN={warn_count}  FAIL={fail_count}  "
        f"SKIP={skip_count}  TOTAL={total_count}  ({elapsed_str})"
    )

    failure_lines: list[str] = _format_failure_details(result)
    if failure_lines:
        lines.extend(failure_lines)

    warning_lines: list[str] = _format_warning_details(result)
    if warning_lines:
        lines.extend(warning_lines)

    return "\n".join(lines)


def _format_failure_details(result: BuildExecutionResult) -> list[str]:
    lines: list[str] = []
    has_failures: bool = False

    model_result: ModelExecutionResult
    for model_result in result.model_results:
        if model_result.status != ExecutionStatus.FAILED:
            continue
        if not has_failures:
            lines.append("")
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

    test_r: SqlTestExecutionResult
    for test_r in result.test_results:
        if test_r.outcome == SqlTestOutcome.PASS:
            continue
        if not has_failures:
            lines.append("")
            lines.append("Failures:")
            lines.append("")
            has_failures = True
        lines.append(f"  {test_r.test_name}  (test)")
        if test_r.error_message is not None:
            lines.append(f"    {test_r.error_message}")
        lines.append("")

    return lines


def _format_warning_details(result: BuildExecutionResult) -> list[str]:
    lines: list[str] = []
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
                lines.append("")
                lines.append("Warnings:")
                lines.append("")
                has_warnings = True
            lines.append(f"  {model_result.model_name}")
            line: str
            for line in model_warnings:
                lines.append(line)
            lines.append("")

    return lines


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
    if materialization_type == MaterializationType.CUSTOM:
        return "custom"
    return "table"


def _resolve_annotation(plan_entry: ModelPlanEntry | None) -> str:
    if plan_entry is None:
        return ""
    is_incremental: bool = (
        plan_entry.action in INCREMENTAL_ACTIONS
        or plan_entry.materialization_type == MaterializationType.INCREMENTAL
    )
    if not is_incremental:
        return ""
    parts: list[str] = []
    if plan_entry.incremental_strategy:
        parts.append(plan_entry.incremental_strategy)
    return ", ".join(parts)


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
        label: str = _phase_label(_phase, has_delta_audits=has_delta, batch_count=len(results))
        entries.append(
            _AuditDisplayEntry(
                label=label,
                display_name=display_name,
                outcome=worst,
                total_row_count=total_rows,
                batch_pass=pass_count,
                batch_total=len(results),
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


def _phase_label(phase: str, *, has_delta_audits: bool, batch_count: int) -> str:
    """Return the audit type label, annotated with phase when delta audits are present."""

    if not has_delta_audits:
        return "audit"
    if phase == AuditRunScope.DELTA_AND_FINAL:
        return "audit (d)"
    return "audit (f)"


def _truncate_name(name: str, width: int) -> str:
    """Truncate a display name to fit within the given width."""

    if len(name) <= width:
        return name
    return name[: width - 3] + "..."
