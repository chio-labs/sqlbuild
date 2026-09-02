"""Structured logging handler for compute diagnostic JSONL."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import cast

from sqlbuild.diagnostics.classes.diagnostic_record_redactor import DiagnosticRecordRedactor
from sqlbuild.diagnostics.constants import (
    LOGGER_PREFIX,
    LOGGER_ROOT_NAME,
    REDACTED_SQL_LOG_MESSAGE,
    SQL_DIGEST_FIELD,
    SQL_PRIVATE_RECORD_FIELD,
    SQL_PRIVATE_RECORD_MARKER,
)
from sqlbuild.observability import DiagnosticLog
from sqlbuild.runtime.compute_logs.constants import SQL_LOG_RECORD_FIELD
from sqlbuild.runtime.compute_logs.types import ComputeLogStorage
from sqlbuild.runtime.observability.types import JSONValue

_IDENTITY_FIELDS: tuple[str, ...] = (
    "invocation_id",
    "run_id",
    "resource_id",
    "resource_attempt_id",
    "operation_id",
    "statement_id",
    "log_stream_id",
)
_SQL_SAFE_FIELDS: frozenset[str] = frozenset(
    ("sql_action", "sql_digest", "sql_intent", "sql_query_id")
)


class ComputeDiagnosticLogHandler(logging.Handler):
    """Retain safe structured SQLBuild records without changing existing handlers."""

    def __init__(
        self,
        *,
        storage: ComputeLogStorage,
        invocation_id: str,
        include_sql_text: bool = False,
        failure_callback: Callable[[Exception], None] | None = None,
    ) -> None:
        super().__init__(level=logging.DEBUG)
        self._storage: ComputeLogStorage = storage
        self._invocation_id: str = invocation_id
        self._failure_callback: Callable[[Exception], None] | None = failure_callback
        self._include_sql_text: bool = include_sql_text
        self._failed: bool = False

    def emit(self, record: logging.LogRecord) -> None:
        """Convert eligible records while excluding SQL and arbitrary parameter fields."""

        if self._failed or not isinstance(record.name, str):
            return
        internal: bool = record.name == LOGGER_ROOT_NAME or record.name.startswith(LOGGER_PREFIX)
        if not internal and record.levelno < logging.INFO:
            return
        contains_sql: bool = (
            SQL_DIGEST_FIELD in record.__dict__ or SQL_LOG_RECORD_FIELD in record.__dict__
        )
        trusted_private_sql: bool = (
            record.__dict__.get(SQL_PRIVATE_RECORD_FIELD) is SQL_PRIVATE_RECORD_MARKER
        )
        if self._include_sql_text and contains_sql and SQL_LOG_RECORD_FIELD not in record.__dict__:
            return
        structured: dict[str, object] = {
            key: value
            for key, value in record.__dict__.items()
            if key.startswith("sqlbuild_") and key != SQL_LOG_RECORD_FIELD
        }
        identities: dict[str, str | None] = {}
        for field_name in _IDENTITY_FIELDS:
            raw_value: object = structured.get(f"sqlbuild_{field_name}")
            identities[field_name] = str(raw_value) if raw_value is not None else None
        identities["invocation_id"] = identities["invocation_id"] or self._invocation_id
        fields: dict[str, JSONValue] = {}
        for safe_name in (
            "sql_action",
            "sql_digest",
            "sql_intent",
            "sql_query_id",
            "channel",
            "subscriber",
            "error_type",
        ):
            raw_value = structured.get(f"sqlbuild_{safe_name}")
            safe_value: object = DiagnosticRecordRedactor.value(name=safe_name, value=raw_value)
            if isinstance(safe_value, (str, int, float, bool)) or safe_value is None:
                if safe_value is not None:
                    fields[safe_name] = safe_value
        try:
            message: str = (
                REDACTED_SQL_LOG_MESSAGE
                if contains_sql
                else DiagnosticRecordRedactor.text(record.getMessage())
            )
            logger_name: str = "sqlbuild.sql" if contains_sql else record.name
            if contains_sql:
                fields = {key: value for key, value in fields.items() if key in _SQL_SAFE_FIELDS}
                if not trusted_private_sql:
                    identities = {field_name: None for field_name in _IDENTITY_FIELDS}
                identities["invocation_id"] = self._invocation_id
                if self._include_sql_text and SQL_LOG_RECORD_FIELD in record.__dict__:
                    fields["sql_text"] = str(record.__dict__[SQL_LOG_RECORD_FIELD])
            elif not internal:
                fields = cast(dict[str, JSONValue], DiagnosticRecordRedactor.extras(record))
            diagnostic: DiagnosticLog = DiagnosticLog(
                schema_version=1,
                producer="sqlbuild",
                producer_version=_sqlbuild_version(),
                occurred_at=datetime.fromtimestamp(record.created, tz=UTC),
                severity=_severity(record.levelno),
                logger=logger_name,
                source="python_logging",
                message=message,
                fields=fields,
                **identities,
            )
        except Exception:
            return
        try:
            self._storage.append_diagnostic(invocation_id=self._invocation_id, record=diagnostic)
        except Exception as error:
            self._failed = True
            if self._failure_callback is not None:
                self._failure_callback(error)


def _severity(level: int) -> str:
    if level >= logging.CRITICAL:
        return "critical"
    if level >= logging.ERROR:
        return "error"
    if level >= logging.WARNING:
        return "warning"
    if level >= logging.INFO:
        return "info"
    return "debug"


def _sqlbuild_version() -> str:
    try:
        return version("sqlbuild")
    except PackageNotFoundError:
        return "unknown"
