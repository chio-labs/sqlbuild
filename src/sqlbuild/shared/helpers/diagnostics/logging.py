"""Shared diagnostics logging primitives."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from sqlbuild.shared.constants import LOGGER_ROOT_NAME

_EMPTY_CONTEXT: dict[str, object] = {}
_DIAGNOSTICS_CONTEXT: ContextVar[dict[str, object] | None] = ContextVar(
    "sqlbuild_diagnostics_context", default=None
)


def get_diagnostics_logger(name: str | None = None) -> logging.Logger:
    """Return a SQLBuild diagnostics logger."""

    if name is None:
        return logging.getLogger(LOGGER_ROOT_NAME)
    return logging.getLogger(f"{LOGGER_ROOT_NAME}.{name}")


def log_sql(*, logger: logging.Logger, sql: str, action: str = "execute") -> None:
    """Log SQL passed to an adapter or connection."""

    logger.debug(
        f"{action} SQL",
        extra={
            "sqlbuild_sql": sql,
            "sqlbuild_sql_action": action,
            **(_DIAGNOSTICS_CONTEXT.get() or _EMPTY_CONTEXT),
        },
    )


def log_debug_event(logger: logging.Logger, *, message: str, **context: object) -> None:
    """Log a structured diagnostics event without SQL."""

    logger.debug(message, extra=context)


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
