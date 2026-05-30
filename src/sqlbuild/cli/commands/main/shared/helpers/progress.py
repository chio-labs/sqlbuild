"""Build progress output callbacks and summary formatting."""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass
from typing import TextIO

from sqlbuild.adapter.shared.models import LifeCycleEvent
from sqlbuild.adapter.shared.types import LifeCycleEventKind
from sqlbuild.cli.commands.main.helpers.sql_test_progress import (
    format_expectation_detail,
    format_expectation_name,
)
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.models import (
    BuildExecutionResult,
    FunctionExecutionResult,
    SeedExecutionResult,
)
from sqlbuild.executor.build.types import BuildStatus, ExecutionStatus
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.testing.models import SqlTestExecutionResult, StepResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.shared.helpers.cli_style import CliStyle
from sqlbuild.shared.helpers.coded_errors import format_coded_error
from sqlbuild.shared.helpers.materialization_labels import (
    materialization_type_display,
    model_execution_annotation,
    model_resource_type,
)
from sqlbuild.shared.types import ExecutionResourceKind

_TYPE_WIDTH: int = 10
_MAX_NAME_WIDTH: int = 60
_MIN_NAME_WIDTH: int = 20
_NAME_PADDING: int = 2
_SUB_INDENT: int = 2
_SPINNER_TICK_SECONDS: float = 0.1
_MAX_ERROR_LINES: int = 4
_MAX_ERROR_LINE_LENGTH: int = 160
_ACTIVE_SPINNER_FRAMES: tuple[str, ...] = (
    "⠋",
    "⠙",
    "⠹",
    "⠸",
    "⠼",
    "⠴",
    "⠦",
    "⠧",
    "⠇",
    "⠏",
)


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


class BuildProgressCallbacks:
    """Encapsulates live build progress output state and callbacks."""

    def __init__(
        self,
        *,
        plan: PlanOutput,
        use_color: bool,
        verbose: bool = False,
        debug: bool = False,
    ) -> None:
        self._model_entry_map: dict[str, ModelPlanEntry] = {
            entry.name: entry for entry in plan.model_entries
        }
        self._test_results_by_model: dict[str, SqlTestExecutionResult] = {}
        self._total: int = (
            len(plan.model_entries)
            + len(plan.seed_entries)
            + len(plan.function_entries)
            + sum(
                1
                for key in plan.execution_order
                if key.resource_type == CompiledResourceType.SOURCE
                and plan.source_map.get(key.name) is not None
                and plan.source_map[key.name].loader is not None
            )
        )
        self._counter: int = 0
        self._use_color: bool = use_color
        self._style: CliStyle = CliStyle(use_color=use_color)
        self._verbose: bool = verbose
        self._debug: bool = debug
        self._is_tty: bool = hasattr(sys.stdout, "isatty") and sys.stdout.isatty() and not debug
        self._stream = sys.stderr if debug else sys.stdout
        self._start_time: float = time.monotonic()
        self._current_node_name: str = ""
        self._current_node_type: ExecutionResourceKind = ExecutionResourceKind.TABLE
        self._current_sub_message: str = ""
        self._spinner_frame_index: int = 0
        self._write_lock: threading.Lock = threading.Lock()
        self._spinner_stop_event: threading.Event | None = None
        self._spinner_thread: threading.Thread | None = None
        self._cursor_hidden: bool = False

        ctr_width: int = len(str(self._total)) * 2 + 1
        self._prefix_width: int = 2 + ctr_width + 2

        max_name_len: int = 0
        entry: ModelPlanEntry
        for entry in plan.model_entries:
            annotation: str = model_execution_annotation(entry)
            display_name: str = entry.name
            if annotation:
                display_name = f"{entry.name}  ({annotation})"
            max_name_len = max(max_name_len, len(display_name))
        seed_entry: object
        for seed_entry in plan.seed_entries:
            max_name_len = max(max_name_len, len(getattr(seed_entry, "name", str(seed_entry))))
        function_entry: object
        for function_entry in plan.function_entries:
            max_name_len = max(
                max_name_len, len(getattr(function_entry, "name", str(function_entry)))
            )
        test_entry: object
        for test_entry in plan.test_entries:
            max_name_len = max(max_name_len, len(getattr(test_entry, "name", str(test_entry))))
            chain_step: object
            for chain_step in getattr(test_entry, "chain", ()):
                if getattr(chain_step, "expected_cte_sql", None):
                    max_name_len = max(
                        max_name_len,
                        len(format_expectation_name(str(getattr(chain_step, "model_name", "")))),
                    )
            assertion: object
            for assertion in getattr(test_entry, "assertions", ()):
                max_name_len = max(
                    max_name_len,
                    len(format_expectation_name(f"assertion {getattr(assertion, 'name', '')}")),
                )
        self._name_width: int = max(max_name_len + _NAME_PADDING, _MIN_NAME_WIDTH)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._start_time

    def _write_sql_block(self, sql: str) -> None:
        """Write a SQL block with minimal indent and dim styling."""

        self._stream.write("\n")
        sql_line: str
        for sql_line in _format_display_sql(sql).split("\n"):
            styled: str = self._style.muted(f"    {sql_line}")
            self._stream.write(f"{styled}\n")
        self._stream.write("\n")

    def _write_log_block(self, message: str) -> None:
        """Write a log message with indent and muted styling."""

        lines: list[str] = message.splitlines() or [""]
        prefix: str = self._style.log_label("    log  ")
        first_content: str = self._style.muted(lines[0])
        styled_first: str = f"{prefix}{first_content}"
        self._stream.write(f"\n{styled_first}\n")
        line: str
        for line in lines[1:]:
            continuation: str = f"         {line}"
            styled_continuation: str = self._style.muted(continuation)
            self._stream.write(f"{styled_continuation}\n")

    def on_node_start(self, name: str, resource_kind: ExecutionResourceKind) -> None:
        self._current_node_name = name
        self._current_node_type = resource_kind
        self._current_sub_message = ""
        if self._is_tty:
            self._hide_cursor()
            self._write_spinner_line()
            self._start_spinner_loop()

    def on_sub_progress(self, message: str) -> None:
        self._current_sub_message = message
        if self._is_tty:
            self._write_spinner_line()

    def _write_spinner_line(self) -> None:
        ctr: str = f"{self._counter + 1}/{self._total}".rjust(len(str(self._total)) * 2 + 1)
        display_type: str = materialization_type_display(self._current_node_type)
        status: str = self._style.status(_ACTIVE_SPINNER_FRAMES[self._spinner_frame_index])
        self._spinner_frame_index = (self._spinner_frame_index + 1) % len(_ACTIVE_SPINNER_FRAMES)
        name_display: str = _truncate_name(self._current_node_name, self._name_width)
        if self._current_sub_message:
            name_display = _truncate_name(
                f"{self._current_node_name}  {self._current_sub_message}", self._name_width
            )
        nw: int = self._name_width
        line: str = f"  {ctr}  {display_type:<{_TYPE_WIDTH}}{name_display:<{nw}} {status}"
        with self._write_lock:
            self._stream.write(f"\r\033[K{line}")
            self._stream.flush()

    def _start_spinner_loop(self) -> None:
        self._stop_spinner_loop()
        stop_event: threading.Event = threading.Event()
        self._spinner_stop_event = stop_event
        spinner_thread: threading.Thread = threading.Thread(
            target=self._spin_until_stopped,
            args=(stop_event,),
            daemon=True,
        )
        self._spinner_thread = spinner_thread
        spinner_thread.start()

    def _stop_spinner_loop(self) -> None:
        if self._spinner_stop_event is not None:
            self._spinner_stop_event.set()
        if self._spinner_thread is not None and self._spinner_thread.is_alive():
            self._spinner_thread.join(timeout=0.2)
        self._spinner_stop_event = None
        self._spinner_thread = None

    def _spin_until_stopped(self, stop_event: threading.Event) -> None:
        while not stop_event.wait(_SPINNER_TICK_SECONDS):
            self._write_spinner_line()

    def _hide_cursor(self) -> None:
        if self._cursor_hidden:
            return
        with self._write_lock:
            self._stream.write("\033[?25l")
            self._stream.flush()
        self._cursor_hidden = True

    def _show_cursor(self) -> None:
        if not self._cursor_hidden:
            return
        with self._write_lock:
            self._stream.write("\033[?25h")
            self._stream.flush()
        self._cursor_hidden = False

    def on_node_complete(self, node_result: object) -> None:
        if isinstance(node_result, SqlTestExecutionResult):
            step: object
            for step in node_result.step_results:
                if hasattr(step, "model_name"):
                    self._test_results_by_model[step.model_name] = node_result
            return

        self._stop_spinner_loop()
        if self._is_tty:
            with self._write_lock:
                self._stream.write("\r\033[K")
                self._stream.flush()
            self._show_cursor()

        self._counter += 1
        ctr: str = f"{self._counter}/{self._total}".rjust(len(str(self._total)) * 2 + 1)

        if isinstance(node_result, SeedExecutionResult):
            status: str = self._style.status(_execution_status_display(node_result.status))
            duration: str = _format_duration(node_result.duration_ms)
            seed_name: str = _truncate_name(node_result.seed_name, self._name_width)
            self._write_top_level_result_line(
                ctr=ctr,
                resource_type="seed",
                name=seed_name,
                status=status,
                duration=duration,
            )
            if node_result.status == ExecutionStatus.FAILED and node_result.error_message:
                self._write_error_detail(
                    error_code=node_result.error_code,
                    error_message=node_result.error_message,
                    error_help=node_result.error_help,
                )
            self._stream.flush()
            return

        if isinstance(node_result, FunctionExecutionResult):
            status: str = self._style.status(_execution_status_display(node_result.status))
            duration: str = _format_duration(node_result.duration_ms)
            function_name: str = _truncate_name(node_result.function_name, self._name_width)
            self._write_top_level_result_line(
                ctr=ctr,
                resource_type=ExecutionResourceKind.FUNCTION.value,
                name=function_name,
                status=status,
                duration=duration,
            )
            if node_result.status == ExecutionStatus.FAILED and node_result.error_message:
                self._write_error_detail(
                    error_code=node_result.error_code,
                    error_message=node_result.error_message,
                    error_help=node_result.error_help,
                )
            self._stream.flush()
            return

        if isinstance(node_result, LoadExecutionResult):
            status = self._style.status(_execution_status_display(node_result.status))
            duration = _format_duration(node_result.duration_ms)
            source_name: str = _truncate_name(node_result.source_name, self._name_width)
            detail: str = f"  rows={node_result.rows_loaded:,}"
            self._write_top_level_result_line(
                ctr=ctr,
                resource_type=node_result.resource_kind.value,
                name=source_name,
                status=status,
                duration=duration,
                detail=detail,
            )
            event: LifeCycleEvent
            for event in node_result.lifecycle_events:
                if event.kind == LifeCycleEventKind.LOG:
                    self._write_log_block(event.content)
                elif self._verbose and event.kind == LifeCycleEventKind.SQL:
                    self._write_sql_block(event.content)
            if node_result.status == ExecutionStatus.FAILED and node_result.error_message:
                self._write_error_detail(
                    error_code=None,
                    error_message=node_result.error_message,
                    error_help=None,
                )
            self._stream.flush()
            return

        if isinstance(node_result, ModelExecutionResult):
            self._write_model_result(ctr=ctr, model_result=node_result)

    def _write_model_result(self, *, ctr: str, model_result: ModelExecutionResult) -> None:
        plan_entry: ModelPlanEntry | None = self._model_entry_map.get(model_result.model_name)
        display_type: str = model_resource_type(plan_entry)
        annotation: str = model_execution_annotation(plan_entry)
        name_display: str = model_result.model_name
        if annotation:
            name_display = f"{model_result.model_name}  ({annotation})"
        name_display = _truncate_name(name_display, self._name_width)

        status: str = self._style.status(_execution_status_display(model_result.status))
        duration: str = _format_duration(model_result.duration_ms)
        detail: str = ""
        if model_result.status == ExecutionStatus.FAILED and model_result.failed_phase is not None:
            detail = f"  {model_result.failed_phase}"
        elif model_result.status == ExecutionStatus.SKIPPED:
            duration = ""

        self._write_top_level_result_line(
            ctr=ctr,
            resource_type=display_type,
            name=name_display,
            status=status,
            duration=duration,
            detail=detail,
        )
        if model_result.status == ExecutionStatus.FAILED and model_result.error_message:
            self._write_error_detail(
                error_code=model_result.error_code,
                error_message=model_result.error_message,
                error_help=model_result.error_help,
            )

        if self._verbose:
            event: LifeCycleEvent
            for event in _resolve_verbose_events(
                model_result=model_result,
                plan_entry=plan_entry,
            ):
                if event.kind == LifeCycleEventKind.SQL:
                    self._write_sql_block(event.content)
                elif event.kind == LifeCycleEventKind.LOG:
                    self._write_log_block(event.content)

        sub_pad: str = " " * (self._prefix_width + _SUB_INDENT)
        sub_nw: int = self._name_width - _SUB_INDENT

        test_result: SqlTestExecutionResult | None = self._test_results_by_model.get(
            model_result.model_name
        )
        if test_result is not None:
            test_status: str = self._style.status(_test_outcome_display(test_result.outcome))
            test_name: str = test_result.test_name
            self._stream.write(
                f"{sub_pad}{'test':<{_TYPE_WIDTH}}{test_name:<{sub_nw}} {test_status}\n"
            )
            expectation_pad: str = f"{sub_pad}  "
            expectation_type_width: int = _TYPE_WIDTH - 2
            step_result: StepResult
            for step_result in test_result.step_results:
                expectation_status: str = self._style.status(
                    _test_outcome_display(step_result.outcome)
                )
                expectation_name: str = format_expectation_name(step_result.model_name)
                expectation_detail: str = format_expectation_detail(step_result)
                self._stream.write(
                    f"{expectation_pad}{'expect':<{expectation_type_width}}"
                    f"{expectation_name:<{sub_nw}} {expectation_status}{expectation_detail}\n"
                )

        display_audits: list[_AuditDisplayEntry] = _aggregate_audit_results(
            model_result.audit_results
        )

        entry: _AuditDisplayEntry
        for entry in display_audits:
            audit_status: str = self._style.status(_audit_outcome_display(entry.outcome))
            audit_name: str = _truncate_name(entry.display_name, sub_nw)
            audit_detail: str = ""
            if entry.outcome != AuditOutcome.PASS and entry.total_row_count > 0:
                row_label: str = "row" if entry.total_row_count == 1 else "rows"
                audit_detail = f"  {entry.total_row_count} {row_label}"
            if entry.batch_total > 1:
                audit_detail = f"  {entry.batch_pass}/{entry.batch_total}" + audit_detail
            audit_line: str = (
                f"{sub_pad}{entry.label:<{_TYPE_WIDTH}}{audit_name:<{sub_nw}}"
                f" {audit_status}{audit_detail}\n"
            )
            self._stream.write(audit_line)

            if self._verbose and entry.executed_sql is not None:
                self._write_sql_block(entry.executed_sql)

        self._stream.flush()

    def _write_top_level_result_line(
        self,
        *,
        ctr: str,
        resource_type: str,
        name: str,
        status: str,
        duration: str,
        detail: str = "",
    ) -> None:
        nw: int = self._name_width
        self._stream.write(
            f"  {ctr}  {resource_type:<{_TYPE_WIDTH}}{name:<{nw}} {status:<6} {duration}{detail}\n"
        )

    def _write_error_detail(
        self, *, error_code: str | None, error_message: str, error_help: str | None = None
    ) -> None:
        pad: str = " " * self._prefix_width
        label: str = self._style.error_muted("error")
        message: str = _format_result_error(
            error_code=error_code,
            error_message=error_message,
            error_help=error_help,
            use_color=self._use_color,
        )
        line: str
        for line_index, line in enumerate(_format_error_lines(message)):
            display_label: str = label if line_index == 0 else ""
            self._stream.write(f"{pad}{display_label:<{_TYPE_WIDTH - 1}} {line}\n")


def format_build_header(*, command: str, target: str | None, concurrency: int) -> str:
    parts: list[str] = [command]
    context_parts: list[str] = []
    if target is not None:
        context_parts.append(f"target: {target}")
    context_parts.append(f"concurrency: {concurrency}")
    if context_parts:
        parts.append(f"  ({', '.join(context_parts)})")
    return "".join(parts)


def write_execution_header(
    *, stream: TextIO, command: str, target: str | None, concurrency: int, use_color: bool
) -> None:
    """Write the shared execution header for command progress output."""

    style: CliStyle = CliStyle(use_color=use_color)
    header: str = format_build_header(command=command, target=target, concurrency=concurrency)
    stream.write(f"{style.object_name('Execution')}  {style.muted(header)}\n\n")
    stream.flush()


def format_build_footer(
    *,
    result: BuildExecutionResult,
    elapsed: float,
    use_color: bool,
) -> str:
    lines: list[str] = []
    style: CliStyle = CliStyle(use_color=use_color)

    if result.status == BuildStatus.FAILED:
        lines.append(style.error("Completed with errors."))
    elif result.warning_count > 0:
        lines.append(style.warning("Completed with warnings."))
    else:
        lines.append(style.success("Completed successfully."))

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

    function_result: FunctionExecutionResult
    for function_result in result.function_results:
        if function_result.status == ExecutionStatus.SUCCESS:
            pass_count += 1
        elif function_result.status == ExecutionStatus.FAILED:
            fail_count += 1
        elif function_result.status == ExecutionStatus.SKIPPED:
            skip_count += 1
        warn_count += len(function_result.warning_messages)

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

    failure_lines: list[str] = _format_failure_details(result, style=style)
    if failure_lines:
        lines.extend(failure_lines)

    warning_lines: list[str] = _format_warning_details(result, style=style)
    if warning_lines:
        lines.extend(warning_lines)

    return "\n".join(lines)


def _format_failure_details(result: BuildExecutionResult, *, style: CliStyle) -> list[str]:
    lines: list[str] = []
    has_failures: bool = False

    seed_result: SeedExecutionResult
    for seed_result in result.seed_results:
        if seed_result.status != ExecutionStatus.FAILED:
            continue
        if not has_failures:
            lines.append("")
            lines.append(style.error_strong("Failures:"))
            lines.append("")
            has_failures = True
        lines.append(f"  {seed_result.seed_name}  (seed)")
        if seed_result.error_message is not None:
            lines.extend(
                _format_failure_error_block(
                    error_code=seed_result.error_code,
                    error_message=seed_result.error_message,
                    error_help=seed_result.error_help,
                    style=style,
                )
            )
        lines.append("")

    model_result: ModelExecutionResult
    for model_result in result.model_results:
        if model_result.status != ExecutionStatus.FAILED:
            continue
        if not has_failures:
            lines.append("")
            lines.append(style.error_strong("Failures:"))
            lines.append("")
            has_failures = True
        phase_str: str = f"  ({model_result.failed_phase})" if model_result.failed_phase else ""
        lines.append(f"  {model_result.model_name}{phase_str}")
        if model_result.error_message is not None:
            lines.extend(
                _format_failure_error_block(
                    error_code=model_result.error_code,
                    error_message=model_result.error_message,
                    error_help=model_result.error_help,
                    style=style,
                )
            )
        if model_result.staging_relation is not None:
            lines.append(f"    {_inspection_relation_message(model_result.staging_relation)}")
        lines.append("")

    function_result: FunctionExecutionResult
    for function_result in result.function_results:
        if function_result.status != ExecutionStatus.FAILED:
            continue
        if not has_failures:
            lines.append("")
            lines.append(style.error_strong("Failures:"))
            lines.append("")
            has_failures = True
        lines.append(f"  {function_result.function_name}  (function)")
        if function_result.error_message is not None:
            lines.extend(
                _format_failure_error_block(
                    error_code=function_result.error_code,
                    error_message=function_result.error_message,
                    error_help=function_result.error_help,
                    style=style,
                )
            )
        lines.append("")

    test_r: SqlTestExecutionResult
    for test_r in result.test_results:
        if test_r.outcome == SqlTestOutcome.PASS:
            continue
        if not has_failures:
            lines.append("")
            lines.append(style.error_strong("Failures:"))
            lines.append("")
            has_failures = True
        lines.append(f"  {test_r.test_name}  (test)")
        if test_r.error_message is not None:
            lines.extend(
                _format_failure_error_block(
                    error_code=test_r.error_code,
                    error_message=test_r.error_message,
                    error_help=test_r.error_help,
                    style=style,
                )
            )
        lines.append("")

    return lines


def _format_warning_details(result: BuildExecutionResult, *, style: CliStyle) -> list[str]:
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
                lines.append(style.warning_strong("Warnings:"))
                lines.append("")
                has_warnings = True
            lines.append(f"  {model_result.model_name}")
            line: str
            for line in model_warnings:
                lines.append(line)
            lines.append("")

    function_result: FunctionExecutionResult
    for function_result in result.function_results:
        if not function_result.warning_messages:
            continue
        if not has_warnings:
            lines.append("")
            lines.append(style.warning_strong("Warnings:"))
            lines.append("")
            has_warnings = True
        lines.append(f"  {function_result.function_name}  (function)")
        warning_msg: str
        for warning_msg in function_result.warning_messages:
            lines.append(f"    {warning_msg}")
        lines.append("")

    return lines


def _inspection_relation_message(relation_name: str) -> str:
    if relation_name.endswith("__delta"):
        return f"delta table kept for inspection: {relation_name}"
    return f"staging table kept for inspection: {relation_name}"


def _format_failure_error_block(
    *, error_code: str | None, error_message: str, error_help: str | None, style: CliStyle
) -> list[str]:
    lines: list[str] = []
    label: str = style.error_muted("error")
    message: str = _format_result_error(
        error_code=error_code,
        error_message=error_message,
        error_help=error_help,
        use_color=style.use_color,
    )
    formatted_line: str
    for index, formatted_line in enumerate(_format_error_lines(message)):
        display_label: str = label if index == 0 else ""
        lines.append(f"    {display_label:<{_TYPE_WIDTH}}{formatted_line}")
    return lines


def _format_result_error(
    *, error_code: str | None, error_message: str, error_help: str | None, use_color: bool
) -> str:
    if error_code is None:
        return error_message
    return format_coded_error(
        code=error_code,
        message=error_message,
        help=error_help,
        use_color=use_color,
    )


def _format_error_lines(message: str) -> list[str]:
    raw_lines: list[str] = message.splitlines() or [message]
    formatted_lines: list[str] = []
    raw_line: str
    for raw_line in raw_lines[:_MAX_ERROR_LINES]:
        if len(raw_line) <= _MAX_ERROR_LINE_LENGTH:
            formatted_lines.append(raw_line)
            continue
        formatted_lines.append(raw_line[: _MAX_ERROR_LINE_LENGTH - 3] + "...")
    if len(raw_lines) > _MAX_ERROR_LINES and formatted_lines:
        last_line: str = formatted_lines[-1]
        if len(last_line) > _MAX_ERROR_LINE_LENGTH - 3:
            formatted_lines[-1] = last_line[: _MAX_ERROR_LINE_LENGTH - 3] + "..."
        elif not last_line.endswith("..."):
            formatted_lines[-1] = f"{last_line}..."
    return formatted_lines


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


def _phase_label(phase: str, *, has_delta_audits: bool, batch_count: int) -> str:
    """Return the audit type label, annotated with phase when delta audits are present."""

    if not has_delta_audits:
        return "audit"
    if phase == AuditRunScope.DELTA_AND_FINAL:
        return "audit (d)"
    return "audit (f)"


def _resolve_verbose_events(
    *, model_result: ModelExecutionResult, plan_entry: ModelPlanEntry | None
) -> tuple[LifeCycleEvent, ...]:
    if model_result.lifecycle_events:
        return model_result.lifecycle_events
    if plan_entry is not None:
        return (LifeCycleEvent(kind=LifeCycleEventKind.SQL, content=plan_entry.logical_ddl),)
    return ()


def _format_display_sql(sql: str) -> str:
    stripped: str = sql.rstrip()
    if not stripped:
        return sql
    if stripped.endswith(";"):
        return stripped
    return f"{stripped};"


def _truncate_name(name: str, width: int) -> str:
    """Truncate a display name to fit within the given width."""

    if len(name) <= width:
        return name
    return name[: width - 3] + "..."
