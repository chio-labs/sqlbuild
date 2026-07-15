"""Diagnostics console formatter."""

from __future__ import annotations

import logging

from sqlbuild.diagnostics._helpers.logging_formatters import (
    _append_exception,
    _format_console_header,
    _get_record_sql,
    _render_sql_inline,
)
from sqlbuild.presentation.classes.cli_style import CliStyle

_SQL_SEPARATOR: str = "-" * 80


class DiagnosticsConsoleFormatter(logging.Formatter):
    """Format diagnostics records for --debug stderr output."""

    def __init__(self, *, use_color: bool = False) -> None:
        super().__init__()
        self._use_color: bool = use_color

    def format(self, record: logging.LogRecord) -> str:
        header: str = _format_console_header(record=record, use_color=self._use_color)
        sql: str | None = _get_record_sql(record)
        if sql is None:
            return _append_exception(record=record, rendered=header)
        if _render_sql_inline(sql):
            return _append_exception(record=record, rendered=f"{header}  {sql.strip()}")
        style: CliStyle = CliStyle(use_color=self._use_color)
        separator: str = style.muted(_SQL_SEPARATOR)
        return _append_exception(
            record=record,
            rendered=f"{header}\n{separator}\n{sql.rstrip()}\n{separator}",
        )
