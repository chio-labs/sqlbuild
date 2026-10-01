"""Scoped in-process listeners told about every finished outermost statement."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from sqlbuild.runtime.observability.types import StatementListener

_STATEMENT_LISTENERS: ContextVar[tuple[StatementListener, ...]] = ContextVar(
    "sqlbuild_statement_listeners", default=()
)


def notify_statement_finished(*, sql: str) -> None:
    """Tell every listener in this context that ``sql`` finished, successfully or not."""

    listener: StatementListener
    for listener in _STATEMENT_LISTENERS.get():
        listener(sql=sql)


@contextmanager
def statement_listener_scope(listener: StatementListener) -> Iterator[None]:
    """Deliver each finished statement's SQL text to ``listener`` while the scope is open."""

    token: Token[tuple[StatementListener, ...]] = _STATEMENT_LISTENERS.set(
        (*_STATEMENT_LISTENERS.get(), listener)
    )
    try:
        yield
    finally:
        _STATEMENT_LISTENERS.reset(token)
