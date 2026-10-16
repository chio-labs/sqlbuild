"""Structured logging handler for compute diagnostic JSONL."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from functools import cache
from importlib.metadata import PackageNotFoundError, version
from typing import Any, cast

from sqlbuild._native import CURRENT_DIAGNOSTIC_LOG_SCHEMA_VERSION, compute_diagnostic_log_fields
from sqlbuild.runtime.compute_logs.types import ComputeLogStorage
from sqlbuild.runtime.observability.models import DiagnosticLog


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

        if self._failed:
            return
        fields: dict[str, object] | None = compute_diagnostic_log_fields(
            record=record,
            invocation_id=self._invocation_id,
            include_sql_text=self._include_sql_text,
        )
        if fields is None:
            return
        try:
            diagnostic: DiagnosticLog = DiagnosticLog(
                schema_version=CURRENT_DIAGNOSTIC_LOG_SCHEMA_VERSION,
                producer_version=_sqlbuild_version(),
                occurred_at=datetime.fromtimestamp(record.created, tz=UTC),
                **cast(dict[str, Any], fields),
            )
        except Exception:
            return
        try:
            self._storage.append_diagnostic(invocation_id=self._invocation_id, record=diagnostic)
        except Exception as error:
            self._failed = True
            if self._failure_callback is not None:
                self._failure_callback(error)


@cache
def _sqlbuild_version() -> str:
    try:
        return version("sqlbuild")
    except PackageNotFoundError:
        return "unknown"
