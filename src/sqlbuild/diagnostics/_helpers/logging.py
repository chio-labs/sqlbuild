"""Diagnostics logging primitives."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from sqlbuild.diagnostics.constants import SQL_TEXT_FIELD
from sqlbuild.observability import (
    ExecutionIdentity,
    current_execution_identity,
    execution_identity_to_dict,
)

_LOGGER_ROOT_NAME: str = "sqlbuild"
_EMPTY_CONTEXT: dict[str, object] = {}
_DIAGNOSTICS_CONTEXT: ContextVar[dict[str, object] | None] = ContextVar(
    "sqlbuild_diagnostics_context", default=None
)
_SQL_DIAGNOSTIC_SINK: ContextVar[Callable[..., None] | None] = ContextVar(
    "sqlbuild_sql_diagnostic_sink", default=None
)


def _current_identity_context() -> dict[str, object]:
    identity: ExecutionIdentity | None = current_execution_identity()
    if identity is None:
        return {}
    return {f"sqlbuild_{key}": value for key, value in execution_identity_to_dict(identity).items()}


def get_diagnostics_logger(name: str | None = None) -> logging.Logger:
    """Return a SQLBuild diagnostics logger."""

    if name is None:
        return logging.getLogger(_LOGGER_ROOT_NAME)
    return logging.getLogger(f"{_LOGGER_ROOT_NAME}.{name}")


def log_sql(
    *,
    logger: logging.Logger,
    sql: str,
    action: str = "execute",
    intent: str | None = None,
    query_id: str | None = None,
) -> None:
    """Log SQL passed to an adapter or connection."""

    contextual_fields: dict[str, object] = {
        key: value
        for key, value in (_DIAGNOSTICS_CONTEXT.get() or _EMPTY_CONTEXT).items()
        if key != SQL_TEXT_FIELD
    }
    sql_fields: dict[str, object] = {
        "sqlbuild_sql_action": action,
        "sqlbuild_sql_digest": f"sha256:{hashlib.sha256(sql.encode('utf-8')).hexdigest()}",
    }
    if intent is not None:
        sql_fields["sqlbuild_sql_intent"] = intent
    if query_id is not None:
        sql_fields["sqlbuild_sql_query_id"] = query_id
    record_fields: dict[str, object] = {
        **contextual_fields,
        **sql_fields,
        **_current_identity_context(),
    }
    logger.debug(
        f"{action} SQL",
        extra=record_fields,
    )
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
        extra={
            **(_DIAGNOSTICS_CONTEXT.get() or _EMPTY_CONTEXT),
            **context,
            **_current_identity_context(),
        },
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
