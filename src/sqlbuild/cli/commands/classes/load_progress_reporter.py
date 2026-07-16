"""Progress callbacks for sqb load execution."""

from __future__ import annotations

import threading
from typing import TextIO

from sqlbuild.adapter.contract.models import LifeCycleEvent
from sqlbuild.adapter.contract.types import LifeCycleEventKind
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.main.summary_footer import format_summary_footer
from sqlbuild.spec.contracts.models import SourceEntry

_SPINNER_TICK_SECONDS: float = 0.1
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


class LoadProgressReporter:
    """TTY-aware renderer for sqb load execution progress."""

    def __init__(
        self,
        *,
        stream: TextIO,
        use_color: bool,
        source_order: dict[str, int],
        total_count: int,
    ) -> None:
        self._stream: TextIO = stream
        self._style: CliStyle = CliStyle(use_color=use_color)
        self._source_order: dict[str, int] = source_order
        self._total_count: int = total_count
        self._is_tty: bool = stream.isatty()
        self._current_source: SourceEntry | None = None
        self._current_sub_message: str = ""
        self._spinner_frame_index: int = 0
        self._spinner_stop_event: threading.Event | None = None
        self._spinner_thread: threading.Thread | None = None
        self._write_lock: threading.Lock = threading.Lock()
        self._cursor_hidden: bool = False

    def on_start(self, source: SourceEntry) -> None:
        if not self._is_tty:
            return
        self._current_source = source
        self._current_sub_message = ""
        self._hide_cursor()
        self._write_spinner_line()
        self._start_spinner_loop()

    def on_progress(self, *, source: SourceEntry, message: str) -> None:
        if not self._is_tty or self._current_source is None:
            return
        if source.name != self._current_source.name:
            return
        self._current_sub_message = message
        self._write_spinner_line()

    def on_complete(self, result: LoadExecutionResult) -> None:
        self._stop_spinner_loop()
        if self._is_tty:
            with self._write_lock:
                self._stream.write("\r\033[K")
                self._stream.flush()
            self._show_cursor()
        status_text: str = (
            "OK"
            if result.status == ExecutionStatus.SUCCESS
            else "SKIP"
            if result.status == ExecutionStatus.SKIPPED
            else "FAIL"
        )
        status: str = self._style.status(status=status_text)
        duration: str = ""
        if result.duration_ms is not None:
            duration = f"{result.duration_ms / 1000.0:.2f}s"
        rows_loaded: str = f"rows={result.rows_loaded:,}"
        ordinal: int = self._source_order[result.source_name]
        self._stream.write(
            f"  {ordinal}/{self._total_count}  {result.resource_kind.value:<10}"
            f"{result.source_name:<30} {status:<6} {duration}  {rows_loaded}\n"
        )
        event: LifeCycleEvent
        for event in result.lifecycle_events:
            if event.kind == LifeCycleEventKind.LOG:
                self._write_log_block(event.content)
        if result.error_message is not None:
            self._stream.write(self._style.error(f"    {result.error_message}\n"))
        self._stream.flush()

    def _write_spinner_line(self) -> None:
        source: SourceEntry | None = self._current_source
        if source is None:
            return
        ordinal: int = self._source_order[source.name]
        status: str = self._style.status(status=_ACTIVE_SPINNER_FRAMES[self._spinner_frame_index])
        self._spinner_frame_index = (self._spinner_frame_index + 1) % len(_ACTIVE_SPINNER_FRAMES)
        resource_kind: str = (
            "loader" if source.meta.get("sqlbuild_loader_node") is True else "source"
        )
        name_display: str = source.name
        if self._current_sub_message:
            name_display = f"{source.name}  {self._current_sub_message}"
        line: str = (
            f"  {ordinal}/{self._total_count}  {resource_kind:<10}{name_display:<48} {status}"
        )
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

    def _write_log_block(self, message: str) -> None:
        lines: list[str] = message.splitlines() or [""]
        prefix: str = self._style.log_label("    log  ")
        first_content: str = self._style.muted(lines[0])
        self._stream.write(f"\n{prefix}{first_content}\n")
        line: str
        for line in lines[1:]:
            self._stream.write(f"{self._style.muted(f'         {line}')}\n")


def format_load_footer(
    *,
    success_count: int,
    fail_count: int,
    skip_count: int,
    total_count: int,
    elapsed: float,
    use_color: bool,
) -> str:
    style: CliStyle = CliStyle(use_color=use_color)
    completion_message: str = (
        style.success("Completed successfully.")
        if fail_count == 0
        else style.error("Completed with errors.")
    )
    return (
        f"\n{completion_message}\n"
        + format_summary_footer(
            counts=(
                ("PASS", success_count),
                ("WARN", 0),
                ("FAIL", fail_count),
                ("SKIP", skip_count),
                ("TOTAL", total_count),
            ),
            use_color=use_color,
            elapsed=f"{elapsed:.2f}s",
        )
        + "\n"
    )
