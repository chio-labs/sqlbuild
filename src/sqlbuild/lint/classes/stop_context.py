"""Thread-local stop signal for speculative lint runs."""

from contextvars import ContextVar
from threading import Event
from typing import ClassVar


class LintStopContext:
    """Own the stop signal that lets a speculative lint run be abandoned between files."""

    active: ClassVar[ContextVar[Event | None]] = ContextVar("active_lint_stop", default=None)
