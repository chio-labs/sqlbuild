"""User-facing warehouse connection progress messages."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.shared.helpers.colors import dim


class ConnectionProgressReporter:
    """Render simple connection start, success, and failure messages."""

    def __init__(
        self,
        *,
        adapter_name: str,
        stream: TextIO,
        blank_line_after_complete: bool = False,
        use_color: bool = False,
    ) -> None:
        self._adapter_name: str = adapter_name
        self._stream: TextIO = stream
        self._blank_line_after_complete: bool = blank_line_after_complete
        self._use_color: bool = use_color

    def on_connection_start(self, connection_count: int) -> None:
        self._stream.write(f"{self._format_progress(self._start_message(connection_count))}\n")
        self._stream.flush()

    def on_connection_complete(self, connection_count: int, elapsed_seconds: float) -> None:
        del connection_count
        message: str = f"Connected to {self._adapter_name}. ({elapsed_seconds:.2f}s)"
        self._stream.write(f"{self._format_progress(message)}\n")
        if self._blank_line_after_complete:
            self._stream.write("\n")
        self._stream.flush()

    def on_connection_error(self, connection_count: int, elapsed_seconds: float) -> None:
        del connection_count
        self._stream.write(
            f"Failed to connect to {self._adapter_name} after {elapsed_seconds:.2f}s.\n"
        )
        self._stream.flush()

    def _start_message(self, connection_count: int) -> str:
        if connection_count <= 1:
            return f"Connecting to {self._adapter_name}..."
        return f"Connecting to {self._adapter_name} ({connection_count} connections)..."

    def _format_progress(self, message: str) -> str:
        return dim(message) if self._use_color else message
