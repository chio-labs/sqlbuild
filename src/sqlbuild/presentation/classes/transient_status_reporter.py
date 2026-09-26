"""Transient status reporter class."""

from __future__ import annotations

import atexit
from contextlib import AbstractContextManager
from typing import TextIO

from rich.console import Console
from rich.status import Status

from sqlbuild.errors.contracts.exceptions import SharedInputError
from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.classes.transient_line_coordinator import TransientLineCoordinator
from sqlbuild.presentation.main._progress_spinners_disabled import progress_spinners_disabled
from sqlbuild.presentation.main.transient_line_coordinator import shared_transient_line_coordinator


class TransientStatusReporter:
    """Render one transient status line with optional spinner updates."""

    def __init__(
        self,
        *,
        stream: TextIO,
        use_color: bool = False,
        enabled: bool = True,
    ) -> None:
        self._stream: TextIO = stream
        self._lines: TransientLineCoordinator = shared_transient_line_coordinator()
        self._style: CliStyle = CliStyle(use_color=use_color)
        self._enabled: bool = (
            enabled
            and not progress_spinners_disabled()
            and hasattr(stream, "isatty")
            and stream.isatty()
        )
        self._console: Console | None = (
            Console(file=stream, no_color=(not use_color)) if self._enabled else None
        )
        self._status_context: AbstractContextManager[Status] | None = None
        self._status: Status | None = None
        self._active: bool = False
        self._message: str | None = None
        atexit.register(self.close)

    def start(self, message: str) -> None:
        if self._enabled:
            with self._lines.lock:
                self.close()
                self._message = message
                self._enter_status()
                self._lines.claim(stream=self._stream, owner=self)
                self._active = True
            return
        self._active = True
        self._write_message(message=message, dim_output=True)

    def update(self, message: str) -> None:
        if self._enabled:
            with self._lines.lock:
                if self._message is not None:
                    self._message = message
                    if self._status is not None:
                        self._status.update(message)
                    return
        self._write_message(message=message, dim_output=True)

    def complete(self, *, message: str, blank_line_after: bool = False) -> None:
        self.close()
        self._write_message(message=message, dim_output=True)
        if blank_line_after:
            self.write_blank_line()

    def complete_styled(self, *, message: str, blank_line_after: bool = False) -> None:
        """Complete with a pre-styled message written verbatim."""

        self.close()
        self._lines.write_persistent(
            stream=self._stream, text=f"{message}\n" + ("\n" if blank_line_after else "")
        )

    def error(self, message: str) -> None:
        self.close()
        self._write_message(message=message, dim_output=False)

    def close(self) -> None:
        with self._lines.lock:
            self._lines.release(owner=self)
            self._exit_status()
            self._message = None
            self._active = False

    def clear_transient_line(self) -> None:
        """Erase the live status so a persistent line can be written in its place."""

        self._exit_status()

    def redraw_transient_line(self) -> None:
        """Restart the live status below persistent output written while it was active."""

        if self._message is not None and self._status_context is None:
            self._enter_status()

    def report_preflight_progress(self, message: str) -> None:
        """Render one preflight progress update."""

        if message.startswith("Prepared "):
            self.complete(message=message, blank_line_after=True)
            return
        if not self._active:
            self.start(message)
            return
        self.update(message)

    def write_blank_line(self) -> None:
        self._lines.write_persistent(stream=self._stream, text="\n")

    def _enter_status(self) -> None:
        if self._console is None or self._message is None:
            raise SharedInputError(
                "status reporter was enabled without an initialized console",
                code="G001",
            )
        self._status_context = self._console.status(status=self._message, spinner="dots")
        self._status = self._status_context.__enter__()

    def _exit_status(self) -> None:
        if self._status_context is not None:
            self._status_context.__exit__(None, None, None)
            self._status_context = None
            self._status = None

    def _write_message(self, *, message: str, dim_output: bool) -> None:
        formatted_message: str = self._style.muted(message) if dim_output else message
        self._lines.write_persistent(stream=self._stream, text=f"{formatted_message}\n")
