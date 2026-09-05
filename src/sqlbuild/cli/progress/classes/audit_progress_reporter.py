"""Coordinator-safe progress reporting for standalone concurrent audits."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TextIO

from sqlbuild.cli.progress.classes.native_progress_projector import (
    NativeProgressProjector,
    current_native_progress_projector,
)
from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.executor.auditing.main.resource_id import audit_resource_id
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.presentation.classes.cli_style import CliStyle

_LABEL_WIDTH: int = 10
_NAME_WIDTH: int = 50


class AuditProgressReporter:
    """Render aggregate live state and flush completed audit rows in plan order."""

    def __init__(
        self,
        *,
        entries: tuple[AuditPlanEntry, ...],
        worker_limit: int,
        stream: TextIO,
        use_color: bool,
    ) -> None:
        self._entries: tuple[AuditPlanEntry, ...] = entries
        self._worker_limit: int = worker_limit
        self._stream: TextIO = stream
        self._style: CliStyle = CliStyle(use_color=use_color)
        self._is_tty: bool = hasattr(stream, "isatty") and stream.isatty()
        self._projector: NativeProgressProjector | None = current_native_progress_projector()
        self._indexes: dict[str, int] = {
            _entry_resource_id(entry): index for index, entry in enumerate(entries)
        }
        self._completed_by_index: dict[int, AuditExecutionResult | None] = {}
        self._next_index: int = 0
        self._running: int = 0
        self._completed: int = 0
        self._current_group: str | None = None
        self._lock: threading.RLock = threading.RLock()
        self._cursor_hidden: bool = False
        self._on_result: Callable[[AuditExecutionResult], None] | None = None

    def set_result_callback(self, callback: Callable[[AuditExecutionResult], None]) -> None:
        """Install plan-ordered result enrichment before dispatch starts."""

        self._on_result = callback

    def on_item_start(self, entry: AuditPlanEntry) -> None:
        """Record a worker start without mutating one-item spinner state."""

        with self._lock:
            self._running += 1
            self._render_aggregate()

    def on_item_complete(self, result: AuditExecutionResult) -> None:
        """Flush every newly contiguous plan-order result row."""

        with self._lock:
            self._completed_by_index[self._indexes[_result_resource_id(result)]] = result
            self._flush_ready()
            self._render_aggregate()

    def on_item_physical_complete(self, result: AuditExecutionResult) -> None:
        """Update aggregate state immediately without projecting a result row."""

        del result
        with self._lock:
            self._running = max(0, self._running - 1)
            self._completed += 1
            self._render_aggregate()

    def on_item_error(self, entry: AuditPlanEntry) -> None:
        """Advance aggregate and ordering state for a fatal audit exception."""

        with self._lock:
            self._running = max(0, self._running - 1)
            self._completed += 1
            self._completed_by_index[self._indexes[_entry_resource_id(entry)]] = None
            self._flush_ready()
            self._render_aggregate()

    def close(self) -> None:
        """Restore the terminal after the final aggregate update."""

        with self._lock:
            if self._is_tty:
                self._clear_aggregate()
                if self._cursor_hidden:
                    self._stream.write("\033[?25h")
                    self._cursor_hidden = False
                self._stream.flush()

    def _flush_ready(self) -> None:
        while self._next_index in self._completed_by_index:
            result: AuditExecutionResult | None = self._completed_by_index.pop(self._next_index)
            self._next_index += 1
            if result is not None:
                self._write_result(result)

    def _write_result(self, result: AuditExecutionResult) -> None:
        if self._is_tty:
            self._clear_aggregate()
        group_name: str = result.attached_target_name or "(unattached)"
        if group_name != self._current_group:
            prefix: str = "\n" if self._current_group is not None else ""
            self._stream.write(f"{prefix}{self._style.section(group_name)}\n")
            self._current_group = group_name
        status_text: str = {
            AuditOutcome.PASS: "PASS",
            AuditOutcome.WARN: "WARN",
            AuditOutcome.ERROR: "FAIL",
            AuditOutcome.INSUFFICIENT: "INSUFFICIENT",
        }[result.outcome]
        name: str = result.audit_name
        if result.attached_column_name is not None:
            name = f"{name} ({result.attached_column_name})"
        detail: str = ""
        if result.outcome != AuditOutcome.PASS and result.row_count > 0:
            row_label: str = "row" if result.row_count == 1 else "rows"
            detail = f"  {result.row_count} {row_label}"
        if self._projector is not None:
            duration_ms: float | None = self._projector.consume_resource_terminal(
                resource_name=result.audit_name,
                resource_id=_result_resource_id(result),
            )
            if duration_ms is not None:
                detail = f"{detail}  {duration_ms / 1000.0:.2f}s"
        status: str = self._style.status(status=status_text)
        self._stream.write(f"    {'audit':<{_LABEL_WIDTH}}{name:<{_NAME_WIDTH}} {status}{detail}\n")
        self._stream.flush()
        if self._on_result is not None:
            self._on_result(result)

    def _render_aggregate(self) -> None:
        if not self._is_tty:
            return
        if not self._cursor_hidden:
            self._stream.write("\033[?25l")
            self._cursor_hidden = True
        self._clear_aggregate()
        self._stream.write(
            "\r\033[K    audit     "
            f"running {self._running} | completed {self._completed}/{len(self._entries)} "
            f"| workers {self._worker_limit}"
        )
        self._stream.flush()

    def _clear_aggregate(self) -> None:
        self._stream.write("\r\033[K")


def _entry_resource_id(entry: AuditPlanEntry) -> str:
    return audit_resource_id(
        audit_name=entry.name,
        attachment_kind=entry.attachment_kind,
        attached_target_kind=entry.attached_target_kind,
        attached_target_name=entry.attached_target_name,
        attached_column_name=entry.attached_column_name,
    )


def _result_resource_id(result: AuditExecutionResult) -> str:
    return audit_resource_id(
        audit_name=result.audit_name,
        attachment_kind=result.attachment_kind,
        attached_target_kind=result.attached_target_kind,
        attached_target_name=result.attached_target_name,
        attached_column_name=result.attached_column_name,
    )
