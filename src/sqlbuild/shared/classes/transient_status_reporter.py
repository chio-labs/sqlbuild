"""Transient status reporter class."""

from __future__ import annotations

import atexit
from contextlib import AbstractContextManager
from typing import TextIO

from rich.console import Console
from rich.status import Status

from sqlbuild.shared.exceptions.errors import SharedInputError
from sqlbuild.shared.helpers.output.cli_style import CliStyle
from sqlbuild.shared.main.progress_spinners_disabled import progress_spinners_disabled


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
        atexit.register(self.close)

    def start(self, message: str) -> None:
        if self._enabled:
            self.close()
            if self._console is None:
                raise SharedInputError(
                    "status reporter was enabled without an initialized console",
                    code="G001",
                )
            self._status_context = self._console.status(status=message, spinner="dots")
            self._status = self._status_context.__enter__()
            self._active = True
            return
        self._active = True
        self._write_message(message=message, dim_output=True)

    def update(self, message: str) -> None:
        if self._enabled and self._status is not None:
            self._status.update(message)
            return
        self._write_message(message=message, dim_output=True)

    def complete(self, *, message: str, blank_line_after: bool = False) -> None:
        self.close()
        self._write_message(message=message, dim_output=True)
        if blank_line_after:
            self._stream.write("\n")
            self._stream.flush()

    def error(self, message: str) -> None:
        self.close()
        self._write_message(message=message, dim_output=False)

    def close(self) -> None:
        if self._status_context is not None:
            self._status_context.__exit__(None, None, None)
            self._status_context = None
            self._status = None
        self._active = False

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
        self._stream.write("\n")
        self._stream.flush()

    def _write_message(self, *, message: str, dim_output: bool) -> None:
        formatted_message: str = self._style.muted(message) if dim_output else message
        self._stream.write(f"{formatted_message}\n")
        self._stream.flush()
