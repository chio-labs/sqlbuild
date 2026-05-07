"""Shared CLI status rendering helpers."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import TextIO

from rich.console import Console
from rich.status import Status

from sqlbuild.shared.helpers.colors import dim


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
        self._use_color: bool = use_color
        self._enabled: bool = enabled and hasattr(stream, "isatty") and stream.isatty()
        self._console: Console | None = (
            Console(file=stream, no_color=(not use_color)) if self._enabled else None
        )
        self._status_context: AbstractContextManager[Status] | None = None
        self._status: Status | None = None

    def start(self, message: str) -> None:
        if self._enabled:
            self.close()
            assert self._console is not None
            self._status_context = self._console.status(message, spinner="dots")
            self._status = self._status_context.__enter__()
            return
        self._write_message(message, dim_output=True)

    def update(self, message: str) -> None:
        if self._enabled and self._status is not None:
            self._status.update(message)
            return
        self._write_message(message, dim_output=True)

    def complete(self, message: str, *, blank_line_after: bool = False) -> None:
        self.close()
        self._write_message(message, dim_output=True)
        if blank_line_after:
            self._stream.write("\n")
            self._stream.flush()

    def error(self, message: str) -> None:
        self.close()
        self._write_message(message, dim_output=False)

    def close(self) -> None:
        if self._status_context is not None:
            self._status_context.__exit__(None, None, None)
            self._status_context = None
            self._status = None

    def _write_message(self, message: str, *, dim_output: bool) -> None:
        formatted_message: str = dim(message) if dim_output and self._use_color else message
        self._stream.write(f"{formatted_message}\n")
        self._stream.flush()


@contextmanager
def maybe_status(message: str, *, enabled: bool) -> Iterator[None]:
    """Render a stderr spinner for long-running interactive operations."""

    if not enabled or not sys.stderr.isatty():
        yield
        return

    reporter: TransientStatusReporter = TransientStatusReporter(
        stream=sys.stderr,
        enabled=enabled,
    )
    reporter.start(message)
    try:
        yield
    finally:
        reporter.close()
