"""Current event dispatcher entrypoint."""

from sqlbuild.runtime.observability._helpers.dispatcher import (
    current_event_dispatcher as _current_event_dispatcher,
)
from sqlbuild.runtime.observability.classes.event_dispatcher import EventDispatcher


def current_event_dispatcher() -> EventDispatcher | None:
    """Return the dispatcher installed in the current context, if any."""

    return _current_event_dispatcher()
