"""User-facing warehouse connection progress messages."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.shared.classes.transient_status_reporter import TransientStatusReporter


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
        self._status: TransientStatusReporter = TransientStatusReporter(
            stream=stream,
            use_color=use_color,
        )

    def on_connection_start(self, connection_count: int) -> None:
        if self._blank_line_before_start:
            self._stream.write("\n")
            self._stream.flush()
        self._status.start(self._start_message(connection_count))

    def on_connection_complete(self, *, connection_count: int, elapsed_seconds: float) -> None:
        del connection_count
        message: str = f"Connected to {self._adapter_name}. ({elapsed_seconds:.2f}s)"
        self._status.complete(message=message, blank_line_after=self._blank_line_after_complete)

    def on_connection_error(self, *, connection_count: int, elapsed_seconds: float) -> None:
        del connection_count
        self._status.error(
            f"Failed to connect to {self._adapter_name} after {elapsed_seconds:.2f}s."
        )

    def _start_message(self, connection_count: int) -> str:
        if connection_count <= 1:
            return f"Connecting to {self._adapter_name}..."
        return f"Connecting to {self._adapter_name} ({connection_count} connections)..."
