"""Diagnostics console formatter."""

from __future__ import annotations

import logging

from sqlbuild._native import format_diagnostics_console_record


class DiagnosticsConsoleFormatter(logging.Formatter):
    """Format diagnostics records for --debug stderr output."""

    def __init__(self, *, use_color: bool = False) -> None:
        super().__init__()
        self._use_color: bool = use_color

    def format(self, record: logging.LogRecord) -> str:
        rendered: str = format_diagnostics_console_record(record, use_color=self._use_color)
        if record.exc_info is None:
            return rendered
        return f"{rendered}\n{logging.Formatter().formatException(record.exc_info)}"
