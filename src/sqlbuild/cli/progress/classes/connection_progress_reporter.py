"""User-facing warehouse connection progress reporter."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.presentation.classes.cli_style import CliStyle
from sqlbuild.presentation.main.phase_line import format_phase_line


class ConnectionProgressReporter:
    """Render simple connection start, success, and failure messages."""

    def __init__(
        self,
        *,
        adapter_name: str,
        stream: TextIO,
        blank_line_before_start: bool = False,
        blank_line_after_complete: bool = False,
        use_color: bool = False,
    ) -> None:
        self._adapter_name: str = adapter_name
        self._stream: TextIO = stream
        self._blank_line_before_start: bool = blank_line_before_start
        self._blank_line_after_complete: bool = blank_line_after_complete
        self._style: CliStyle = CliStyle(use_color=use_color)

    def on_connection_start(self, connection_count: int) -> None:
        if self._blank_line_before_start:
            self._stream.write("\n")
            self._stream.flush()
        self._write(self._style.muted(self._start_message(connection_count)))

    def on_connection_complete(self, *, connection_count: int, elapsed_seconds: float) -> None:
        del connection_count
        message: str = format_phase_line(
            style=self._style,
            ok=True,
            label="Warehouse connected",
            summary=f"{self._adapter_name}  ({elapsed_seconds:.2f}s)",
        )
        self._write(message)
        if self._blank_line_after_complete:
            self._write("")

    def on_connection_error(self, *, connection_count: int, elapsed_seconds: float) -> None:
        del connection_count
        message: str = format_phase_line(
            style=self._style,
            ok=False,
            label="Warehouse connection failed",
            summary=f"{self._adapter_name}  (after {elapsed_seconds:.2f}s)",
        )
        self._write(message)

    def _start_message(self, connection_count: int) -> str:
        if connection_count <= 1:
            return f"Connecting to {self._adapter_name}..."
        return f"Connecting to {self._adapter_name} ({connection_count} connections)..."

    def _write(self, message: str) -> None:
        self._stream.write(f"{message}\n")
        self._stream.flush()
