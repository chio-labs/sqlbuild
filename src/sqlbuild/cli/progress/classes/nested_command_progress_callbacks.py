"""Progress rendering for grouped audit and test style commands."""

from __future__ import annotations

import threading
from typing import TextIO

from sqlbuild.cli.progress.classes.native_progress_projector import (
    NativeProgressProjector,
    current_native_progress_projector,
)
from sqlbuild.cli.progress.models import NestedProgressChildRow
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.classes.transient_line_coordinator import TransientLineCoordinator
from sqlbuild.presentation.main.inline_error_lines import format_inline_error_lines
from sqlbuild.presentation.main.terminal_columns import terminal_columns
from sqlbuild.presentation.main.transient_line_coordinator import shared_transient_line_coordinator
from sqlbuild.presentation.main.tree_connector import tree_connector

_LABEL_WIDTH: int = 10
_NAME_WIDTH: int = 50
_SPINNER_TICK_SECONDS: float = 0.1
_LIVE_ROW_PADDING: int = 7
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


class NestedCommandProgressCallbacks:
    """Render one live spinner row for all running items and grouped completed rows."""

    def __init__(
        self,
        *,
        total: int,
        label: str,
        stream: TextIO,
        use_color: bool,
        name_width: int = _NAME_WIDTH,
        concurrency: int = 1,
    ) -> None:
        self._total: int = total
        self._label: str = label
        self._stream: TextIO = stream
        self._lines: TransientLineCoordinator = shared_transient_line_coordinator()
        self._use_color: bool = use_color
        self._style: CliStyle = CliStyle(use_color=use_color)
        self._name_width: int = max(_NAME_WIDTH, name_width)
        self._is_tty: bool = hasattr(stream, "isatty") and stream.isatty()
        self._sequential: bool = concurrency <= 1
        self._printed_group: str | None = None
        self._running: dict[str, str] = {}
        self._spinner_frame_index: int = 0
        self._write_lock: threading.RLock = self._lines.lock
        self._spinner_line_active: bool = False
        self._spinner_stop_event: threading.Event | None = None
        self._spinner_thread: threading.Thread | None = None
        self._cursor_hidden: bool = False
        self._projector: NativeProgressProjector | None = current_native_progress_projector()

    def on_item_start(
        self,
        *,
        group_name: str,
        item_name: str,
        canonical_resource_name: str | None = None,
    ) -> None:
        if self._projector is not None:
            self._projector.expect_resource_enrichment(
                resource_name=canonical_resource_name or item_name
            )
        with self._write_lock:
            if self._sequential and not self._running:
                self._clear_live_row()
                self._write_group_header(group_name)
            self._running[item_name] = group_name
            if self._is_tty:
                self._hide_cursor()
                self._spinner_line_active = True
                self._lines.claim(stream=self._stream, owner=self)
                self._draw_spinner_line()
                self._ensure_spinner_loop()

    def on_item_complete(
        self,
        *,
        group_name: str,
        item_name: str,
        status_text: str,
        detail: str = "",
        error_code: str | None = None,
        error_help: str | None = None,
        error_message: str | None = None,
        child_rows: tuple[NestedProgressChildRow, ...] = (),
        canonical_resource_name: str | None = None,
        canonical_resource_id: str | None = None,
    ) -> None:
        duration_ms: float | None = None
        if self._projector is not None:
            duration_ms = self._projector.consume_resource_terminal(
                resource_name=canonical_resource_name or item_name,
                resource_id=canonical_resource_id,
            )
        stopped_thread: threading.Thread | None
        with self._write_lock:
            item_group: str = self._running.pop(item_name, group_name)
            if self._projector is None or duration_ms is not None:
                if duration_ms is not None:
                    detail = f"{detail}  {duration_ms / 1000.0:.2f}s"
                self._clear_live_row()
                self._write_group_header(item_group)
                self._write_completed_item(
                    item_name=item_name,
                    status_text=status_text,
                    detail=detail,
                    error_code=error_code,
                    error_help=error_help,
                    error_message=error_message,
                    child_rows=child_rows,
                )
            stopped_thread = self._refresh_live_row()
            self._stream.flush()
        if stopped_thread is not None and stopped_thread.is_alive():
            stopped_thread.join(timeout=0.2)

    def _write_group_header(self, group_name: str) -> None:
        if group_name == self._printed_group:
            return
        prefix: str = "" if self._printed_group is None else "\n"
        self._printed_group = group_name
        self._stream.write(f"{prefix}{self._style.section(group_name)}\n")
        self._stream.flush()

    def _write_completed_item(
        self,
        *,
        item_name: str,
        status_text: str,
        detail: str,
        error_code: str | None,
        error_help: str | None,
        error_message: str | None,
        child_rows: tuple[NestedProgressChildRow, ...],
    ) -> None:
        status: str = self._style.status(status=status_text)
        self._stream.write(
            f"    {self._label:<{_LABEL_WIDTH}}{item_name:<{self._name_width}} {status}{detail}\n"
        )
        child_row: NestedProgressChildRow
        for index, child_row in enumerate(child_rows):
            child_status: str = self._style.status(status=child_row.status_text)
            last: bool = index == len(child_rows) - 1 and error_message is None
            connector: str = tree_connector(style=self._style, last=last)
            self._stream.write(
                f"      {connector} {child_row.label:<{_LABEL_WIDTH - 2}}"
                f"{child_row.name:<{self._name_width}} "
                f"{child_status}{child_row.detail}\n"
            )
        if error_message is not None:
            self._write_error(
                error_code=error_code,
                error_message=error_message,
                error_help=error_help,
            )

    def _clear_live_row(self) -> None:
        if self._is_tty and self._spinner_line_active:
            self._stream.write("\r\033[K")

    def _refresh_live_row(self) -> threading.Thread | None:
        """Redraw the live row for remaining items, or retire it; return a thread to join."""

        if not self._is_tty:
            return None
        if self._running:
            self._draw_spinner_line()
            return None
        self._spinner_line_active = False
        self._lines.release(owner=self)
        self._show_cursor()
        stopped_thread: threading.Thread | None = self._spinner_thread
        if self._spinner_stop_event is not None:
            self._spinner_stop_event.set()
        self._spinner_stop_event = None
        self._spinner_thread = None
        return stopped_thread

    def _write_error(
        self, *, error_code: str | None, error_message: str, error_help: str | None
    ) -> None:
        pad: str = " " * 6
        connector: str = tree_connector(style=self._style, last=True)
        label_width: int = _LABEL_WIDTH - 2
        label: str = self._style.error_muted(f"{'error':<{label_width}}")
        plain_prefix_width: int = len(pad) + 4 + label_width
        content_width: int = max(terminal_columns() - plain_prefix_width, 1)
        lines: list[str] = format_inline_error_lines(
            error_code=error_code,
            error_message=error_message,
            error_help=error_help,
            content_width=content_width,
            style=self._style,
        )
        continuation_pad: str = " " * plain_prefix_width
        for index, line in enumerate(lines):
            if index == 0:
                self._stream.write(f"{pad}{connector} {label}{line}\n")
            else:
                self._stream.write(f"{continuation_pad}{line}\n")

    def clear_transient_line(self) -> None:
        """Erase the live spinner row so a persistent line can take its place."""

        with self._write_lock:
            self._stream.write("\r\033[K")
            self._stream.flush()

    def redraw_transient_line(self) -> None:
        """Draw the live spinner row again below persistent output."""

        self._write_spinner_line()

    def _write_spinner_line(self) -> None:
        with self._write_lock:
            if self._spinner_line_active:
                self._draw_spinner_line()

    def _draw_spinner_line(self) -> None:
        spinner: str = self._style.status(status=_ACTIVE_SPINNER_FRAMES[self._spinner_frame_index])
        self._spinner_frame_index = (self._spinner_frame_index + 1) % len(_ACTIVE_SPINNER_FRAMES)
        running: tuple[str, ...] = tuple(self._running)
        text: str = (
            running[0] if len(running) == 1 else f"{len(running)} running: {', '.join(running)}"
        )
        name_width: int = max(
            min(self._name_width, terminal_columns() - _LABEL_WIDTH - _LIVE_ROW_PADDING), 1
        )
        name: str = text if len(text) <= name_width else f"{text[: max(name_width - 3, 0)]}..."
        self._stream.write(
            f"\r\033[K    {self._label:<{_LABEL_WIDTH}}{name:<{name_width}} {spinner}"
        )
        self._stream.flush()

    def _ensure_spinner_loop(self) -> None:
        if self._spinner_thread is not None:
            return
        stop_event: threading.Event = threading.Event()
        self._spinner_stop_event = stop_event
        spinner_thread: threading.Thread = threading.Thread(
            target=self._spin_until_stopped,
            args=(stop_event,),
            daemon=True,
        )
        self._spinner_thread = spinner_thread
        spinner_thread.start()

    def _spin_until_stopped(self, stop_event: threading.Event) -> None:
        while not stop_event.wait(_SPINNER_TICK_SECONDS):
            with self._write_lock:
                if not stop_event.is_set() and self._spinner_line_active:
                    self._draw_spinner_line()

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
