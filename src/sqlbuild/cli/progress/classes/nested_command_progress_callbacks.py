"""Progress rendering for grouped audit and test style commands."""

from __future__ import annotations

import threading
from typing import TextIO

from sqlbuild.cli.progress.models import NestedProgressChildRow
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.main.inline_error_lines import format_inline_error_lines
from sqlbuild.presentation.main.terminal_columns import terminal_columns
from sqlbuild.presentation.main.tree_connector import tree_connector

_LABEL_WIDTH: int = 10
_NAME_WIDTH: int = 50
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


class NestedCommandProgressCallbacks:
    """Render one live spinner row and grouped completed rows."""

    def __init__(
        self,
        *,
        total: int,
        label: str,
        stream: TextIO,
        use_color: bool,
        name_width: int = _NAME_WIDTH,
    ) -> None:
        self._total: int = total
        self._label: str = label
        self._stream: TextIO = stream
        self._use_color: bool = use_color
        self._style: CliStyle = CliStyle(use_color=use_color)
        self._name_width: int = max(_NAME_WIDTH, name_width)
        self._is_tty: bool = hasattr(stream, "isatty") and stream.isatty()
        self._counter: int = 0
        self._current_group: str = ""
        self._active_group: str = ""
        self._active_name: str = ""
        self._active_group_is_new: bool = False
        self._spinner_frame_index: int = 0
        self._write_lock: threading.Lock = threading.Lock()
        self._spinner_stop_event: threading.Event | None = None
        self._spinner_thread: threading.Thread | None = None
        self._cursor_hidden: bool = False

    def on_item_start(self, *, group_name: str, item_name: str) -> None:
        self._active_group = group_name
        self._active_name = item_name
        self._active_group_is_new = group_name != self._current_group
        if self._active_group_is_new:
            self._current_group = group_name
            group_header: str = self._style.section(group_name)
            prefix: str = "\n" if self._counter > 0 else ""
            self._stream.write(f"{prefix}{group_header}\n")
            self._stream.flush()
        if self._is_tty:
            self._hide_cursor()
            self._write_spinner_line()
            self._start_spinner_loop()

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
    ) -> None:
        self._stop_spinner_loop()
        if self._is_tty:
            with self._write_lock:
                self._stream.write("\r\033[K")
                self._stream.flush()
            self._show_cursor()

        self._counter += 1

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
        self._stream.flush()

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

    def _write_spinner_line(self) -> None:
        spinner: str = self._style.status(status=_ACTIVE_SPINNER_FRAMES[self._spinner_frame_index])
        self._spinner_frame_index = (self._spinner_frame_index + 1) % len(_ACTIVE_SPINNER_FRAMES)
        name: str = self._active_name
        with self._write_lock:
            self._stream.write(
                f"\r\033[K    {self._label:<{_LABEL_WIDTH}}{name:<{self._name_width}} {spinner}"
            )
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
