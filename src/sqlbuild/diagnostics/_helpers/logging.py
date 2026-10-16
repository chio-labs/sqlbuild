"""Diagnostics logging primitives."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from sqlbuild._native import debug_event_record_fields, sql_log_record
from sqlbuild.runtime.observability.main.current_execution_identity import (
    current_execution_identity,
)
from sqlbuild.runtime.observability.main.execution_identity_to_dict import (
    execution_identity_to_dict,
)
from sqlbuild.runtime.observability.models import ExecutionIdentity

_EMPTY_CONTEXT: dict[str, object] = {}
_DIAGNOSTICS_CONTEXT: ContextVar[dict[str, object] | None] = ContextVar(
    "sqlbuild_diagnostics_context", default=None
)
_SQL_DIAGNOSTIC_SINK: ContextVar[Callable[..., None] | None] = ContextVar(
    "sqlbuild_sql_diagnostic_sink", default=None
)


def _current_identity_fields() -> dict[str, str | None] | None:
    identity: ExecutionIdentity | None = current_execution_identity()
    if identity is None:
        return None
    return execution_identity_to_dict(identity)


def log_sql(
    *,
    logger: logging.Logger,
    sql: str,
    action: str = "execute",
    intent: str | None = None,
    query_id: str | None = None,
) -> None:
    """Log SQL passed to an adapter or connection."""

    message, record_fields = sql_log_record(
        context=_DIAGNOSTICS_CONTEXT.get(),
        identity=_current_identity_fields(),
        sql=sql,
        action=action,
        intent=intent,
        query_id=query_id,
    )
    logger.debug(message, extra=record_fields)
    sql_sink: Callable[..., None] | None = _SQL_DIAGNOSTIC_SINK.get()
    if sql_sink is not None:
        sql_sink(logger=logger, sql=sql, fields=record_fields)


def set_sql_diagnostic_sink(
    *,
    sink: Callable[..., None] | None = None,
    token: Token[Callable[..., None] | None] | None = None,
) -> Token[Callable[..., None] | None] | None:
    """Set or restore the invocation-local private SQL diagnostic destination."""

    if token is not None:
        _SQL_DIAGNOSTIC_SINK.reset(token)
        return None
    return _SQL_DIAGNOSTIC_SINK.set(sink)


def log_debug_event(*, logger: logging.Logger, message: str, **context: object) -> None:
    """Log a structured diagnostics event without SQL."""

    logger.debug(
        message,
        extra=debug_event_record_fields(
            context=_DIAGNOSTICS_CONTEXT.get(),
            event_fields=context,
            identity=_current_identity_fields(),
        ),
    )


@contextmanager
def diagnostics_context(**context: object) -> Iterator[None]:
    """Apply debug context to nested diagnostics events in the current thread."""

    current_context: dict[str, object] = dict(_DIAGNOSTICS_CONTEXT.get() or _EMPTY_CONTEXT)
    current_context.update({key: value for key, value in context.items() if value is not None})
    token: Token[dict[str, object] | None] = _DIAGNOSTICS_CONTEXT.set(current_context)
    try:
        yield
    finally:
        _DIAGNOSTICS_CONTEXT.reset(token)
