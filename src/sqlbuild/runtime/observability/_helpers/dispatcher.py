"""Scoped current event dispatcher primitives."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

from sqlbuild.runtime.observability.classes.event_dispatcher import EventDispatcher

_CURRENT_EVENT_DISPATCHER: ContextVar[EventDispatcher | None] = ContextVar(
    "sqlbuild_event_dispatcher", default=None
)


def current_event_dispatcher() -> EventDispatcher | None:
    return _CURRENT_EVENT_DISPATCHER.get()


@contextmanager
def dispatcher_scope(dispatcher: EventDispatcher) -> Iterator[EventDispatcher]:
    token: Token[EventDispatcher | None] = _CURRENT_EVENT_DISPATCHER.set(dispatcher)
    try:
        yield dispatcher
    finally:
        _CURRENT_EVENT_DISPATCHER.reset(token)
