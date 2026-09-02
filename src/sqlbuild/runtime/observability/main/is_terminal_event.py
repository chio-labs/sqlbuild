"""Lifecycle terminal-semantics entrypoint."""

from sqlbuild.runtime.observability._helpers.observability import (
    is_terminal_event as _is_terminal_event,
)
from sqlbuild.runtime.observability.models import LifecycleEvent


def is_terminal_event(event: LifecycleEvent) -> bool:
    """Return whether the fact closes its correlated lifecycle scope."""

    return _is_terminal_event(event)
