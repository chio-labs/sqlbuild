"""Event dispatcher scope entrypoint."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlbuild.runtime.observability._helpers.dispatcher import dispatcher_scope as _dispatcher_scope
from sqlbuild.runtime.observability.classes.event_dispatcher import EventDispatcher


@contextmanager
def dispatcher_scope(dispatcher: EventDispatcher) -> Iterator[EventDispatcher]:
    """Install an explicit dispatcher for a nested framework boundary."""

    with _dispatcher_scope(dispatcher) as installed:
        yield installed
