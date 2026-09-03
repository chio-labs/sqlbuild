"""Invocation-scoped diagnostic logging ownership."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextvars import Token
from types import TracebackType

from sqlbuild.diagnostics._helpers.logging import set_sql_diagnostic_sink
from sqlbuild.diagnostics.classes.diagnostics_console_formatter import DiagnosticsConsoleFormatter
from sqlbuild.diagnostics.classes.dynamic_stderr_handler import DynamicStderrHandler
from sqlbuild.diagnostics.classes.log_record_route_filter import LogRecordRouteFilter
from sqlbuild.diagnostics.constants import (
    SQL_PRIVATE_RECORD_FIELD,
    SQL_PRIVATE_RECORD_MARKER,
    SQL_TEXT_FIELD,
)
from sqlbuild.diagnostics.models import DiagnosticRoutingOptions
from sqlbuild.runtime.compute_logs.classes.diagnostic_log_handler import (
    ComputeDiagnosticLogHandler,
)
from sqlbuild.runtime.compute_logs.types import ComputeLogStorage

_ROUTE_OWNER_FIELD: str = "_sqlbuild_diagnostic_route_owner"


class InvocationDiagnosticRouting:
    """Own and restore all Python logging routes for one active invocation."""

    def __init__(
        self,
        *,
        invocation_id: str,
        options: DiagnosticRoutingOptions,
        storage: ComputeLogStorage | None = None,
        failure_callback: Callable[[Exception], None] | None = None,
    ) -> None:
        self._invocation_id: str = invocation_id
        self._options: DiagnosticRoutingOptions = options
        self._storage: ComputeLogStorage | None = storage
        self._failure_callback: Callable[[Exception], None] | None = failure_callback
        self._root: logging.Logger = logging.getLogger()
        self._internal: logging.Logger = logging.getLogger("sqlbuild")
        self._root_state: tuple[int, bool] | None = None
        self._internal_state: tuple[int, bool] | None = None
        self._handlers: list[logging.Handler] = []
        self._private_sql_handlers: list[logging.Handler] = []
        self._suspended_handlers: list[tuple[int, logging.Handler]] = []
        self._sql_token: Token[Callable[..., None] | None] | None = None

    def __enter__(self) -> InvocationDiagnosticRouting:
        """Install routes after preserving exact prior logger state."""

        self._root_state = (self._root.level, self._root.propagate)
        self._internal_state = (self._internal.level, self._internal.propagate)
        for index, handler in enumerate(tuple(self._root.handlers)):
            if getattr(handler, _ROUTE_OWNER_FIELD, False):
                try:
                    self._root.removeHandler(handler)
                except Exception as error:
                    try:
                        self._root.handlers.remove(handler)
                    except Exception as fallback_error:
                        self._report(fallback_error)
                    self._report(error)
                self._suspended_handlers.append((index, handler))
        self._handlers = self._build_handlers()
        for handler in self._handlers:
            setattr(handler, _ROUTE_OWNER_FIELD, True)
            self._root.addHandler(handler)
        self._root.setLevel(min(self._root.level, logging.INFO))
        self._internal.setLevel(logging.DEBUG)
        self._internal.propagate = True
        sql_sink: Callable[..., None] | None = (
            self._emit_private_sql if self._options.include_sql_text else None
        )
        self._sql_token = set_sql_diagnostic_sink(sink=sql_sink)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Restore prior state even when setup, execution, or cleanup fails."""

        _ = (exc_type, exc_value, traceback)
        if self._sql_token is not None:
            try:
                set_sql_diagnostic_sink(token=self._sql_token)
            except Exception as error:
                self._report(error)
            self._sql_token = None
        if self._internal_state is not None:
            level, propagate = self._internal_state
            try:
                self._internal.setLevel(level)
                self._internal.propagate = propagate
            except Exception as error:
                self._report(error)
        for owned_handler in self._handlers:
            try:
                self._root.removeHandler(owned_handler)
            except Exception as error:
                try:
                    self._root.handlers.remove(owned_handler)
                except Exception as fallback_error:
                    self._report(fallback_error)
                self._report(error)
        if self._root_state is not None:
            level, propagate = self._root_state
            try:
                self._root.setLevel(level)
                self._root.propagate = propagate
            except Exception as error:
                self._report(error)
        for handler in self._handlers:
            try:
                handler.close()
            except Exception as error:
                self._report(error)
        for index, handler in self._suspended_handlers:
            try:
                insertion_index: int = min(index, len(self._root.handlers))
                self._root.handlers.insert(insertion_index, handler)
            except Exception as error:
                self._report(error)
        self._handlers = []
        self._private_sql_handlers = []
        self._suspended_handlers = []

    def _build_handlers(self) -> list[logging.Handler]:
        handlers: list[logging.Handler] = []
        if self._storage is not None:
            diagnostic_handler: ComputeDiagnosticLogHandler = ComputeDiagnosticLogHandler(
                storage=self._storage,
                invocation_id=self._invocation_id,
                include_sql_text=self._options.include_sql_text,
                failure_callback=self._failure_callback,
            )
            handlers.append(diagnostic_handler)
            self._private_sql_handlers.append(diagnostic_handler)
        console_handler: DynamicStderrHandler = DynamicStderrHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(DiagnosticsConsoleFormatter(use_color=self._options.use_color))
        console_handler.addFilter(
            LogRecordRouteFilter(
                internal_only=False,
                allow_internal=self._options.debug_console,
                include_sql_text=False,
            )
        )
        handlers.append(console_handler)
        return handlers

    def _emit_private_sql(
        self, *, logger: logging.Logger, sql: str, fields: dict[str, object]
    ) -> None:
        private_fields: dict[str, object] = {
            **fields,
            SQL_TEXT_FIELD: sql,
            SQL_PRIVATE_RECORD_FIELD: SQL_PRIVATE_RECORD_MARKER,
        }
        record: logging.LogRecord = logging.LogRecord(
            name=logger.name,
            level=logging.DEBUG,
            pathname="",
            lineno=0,
            msg="SQL diagnostic omitted",
            args=(),
            exc_info=None,
        )
        record.__dict__.update(private_fields)
        for handler in tuple(self._private_sql_handlers):
            try:
                handler.handle(record)
            except Exception as error:
                self._report(error)

    def _report(self, error: Exception) -> None:
        if self._failure_callback is None:
            return
        try:
            self._failure_callback(error)
        except Exception:
            pass
