"""Diagnostics logging formatters."""

from __future__ import annotations

import logging

from sqlbuild.diagnostics.helpers.constants import (
    FILE_LOG_DATE_FORMAT,
    LOGGER_ROOT_NAME,
    SQL_SEPARATOR,
)
from sqlbuild.shared.helpers.output.cli_style import CliStyle

_SQL_EVENT_FIELD: str = "sqlbuild_sql"


class DiagnosticsFileFormatter(logging.Formatter):
    """Format diagnostics records for target/sqlbuild.log."""

    def format(self, record: logging.LogRecord) -> str:
        prefix: str = _format_prefix(
            record=record, date_text=self.formatTime(record, FILE_LOG_DATE_FORMAT)
        )
        sql: str | None = _get_record_sql(record)
        if sql is None:
            return _append_exception(record=record, rendered=f"{prefix} {record.getMessage()}")
        return _append_exception(
            record=record,
            rendered=(
                f"{prefix} {record.getMessage()}\n{SQL_SEPARATOR}\n{sql.rstrip()}\n{SQL_SEPARATOR}"
            ),
        )


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
        separator: str = style.muted(SQL_SEPARATOR)
        return _append_exception(
            record=record,
            rendered=f"{header}\n{separator}\n{sql.rstrip()}\n{separator}",
        )


def _format_prefix(*, record: logging.LogRecord, date_text: str) -> str:
    return (
        f"{date_text}.{int(record.msecs):03d} {record.levelname} {_short_logger_name(record.name)}"
    )


def _short_logger_name(name: str) -> str:
    prefix: str = f"{LOGGER_ROOT_NAME}."
    if name.startswith(prefix):
        return name.removeprefix(prefix)
    return name


def _format_console_header(*, record: logging.LogRecord, use_color: bool) -> str:
    style: CliStyle = CliStyle(use_color=use_color)
    level_tag: str = f"[{record.levelname.lower()}]"
    context_message: str | None = _format_context_message(record=record, use_color=use_color)
    if context_message is None:
        scope: str = _short_logger_name(record.name)
        colored_scope: str = style.object_name(scope)
        context_message = f"{colored_scope} {_normalize_console_message(record.getMessage())}"
    if not use_color:
        return f"{level_tag} {context_message}"
    return f"{style.log_label(level_tag)} {context_message}"


def _normalize_console_message(message: str) -> str:
    return message.replace(" SQL", " sql")


def _render_sql_inline(sql: str) -> bool:
    normalized: str = sql.strip().upper()
    return normalized in {"BEGIN", "COMMIT", "ROLLBACK"}


def _format_context_message(*, record: logging.LogRecord, use_color: bool) -> str | None:
    subject: object = getattr(record, "sqlbuild_subject", None)
    if not isinstance(subject, str):
        return None
    parts: list[str] = [subject]
    name: object = getattr(record, "sqlbuild_name", None)
    if isinstance(name, str):
        parts.append(_colorable_name(name=name, use_color=use_color))
    event: object = getattr(record, "sqlbuild_event", None)
    if isinstance(event, str):
        parts.append(event)
    parts.extend(_format_context_tokens(record))
    message: str = _normalize_console_message(record.getMessage())
    if message:
        parts.append(message)
    return " ".join(parts)


def _format_context_tokens(record: logging.LogRecord) -> list[str]:
    token_specs: tuple[tuple[str, str], ...] = (
        ("sqlbuild_phase", "phase"),
        ("sqlbuild_kind", "kind"),
        ("sqlbuild_action_name", "action"),
        ("sqlbuild_audit_name", "audit"),
        ("sqlbuild_column_name", "column"),
        ("sqlbuild_window", "window"),
        ("sqlbuild_status", "status"),
    )
    rendered: list[str] = []
    field_name: str
    label: str
    for field_name, label in token_specs:
        value: object = getattr(record, field_name, None)
        if isinstance(value, str):
            rendered.append(f"{label}={value}")
    duration_ms: object = getattr(record, "sqlbuild_duration_ms", None)
    if isinstance(duration_ms, int):
        rendered.append(f"duration={duration_ms / 1000:.2f}s")
    return rendered


def _colorable_name(*, name: str, use_color: bool) -> str:
    return CliStyle(use_color=use_color).object_name(name)


def _get_record_sql(record: logging.LogRecord) -> str | None:
    value: object = getattr(record, _SQL_EVENT_FIELD, None)
    if isinstance(value, str):
        return value
    return None


def _append_exception(*, record: logging.LogRecord, rendered: str) -> str:
    if record.exc_info is None:
        return rendered
    exception_text: str = logging.Formatter().formatException(record.exc_info)
    return f"{rendered}\n{exception_text}"
