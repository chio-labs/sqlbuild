"""Thread-local stop signal for speculative lint runs."""

from contextvars import ContextVar
from threading import Event
from typing import ClassVar

from sqlbuild.lint.exceptions import LintStoppedError


class LintStopContext:
    """Own the stop signal that lets a speculative lint run be abandoned between files."""

    active: ClassVar[ContextVar[Event | None]] = ContextVar("active_lint_stop", default=None)

    @staticmethod
    def check() -> None:
        """Abandon a speculative lint run on this thread once its owner no longer needs it."""

        stop: Event | None = LintStopContext.active.get()
        if stop is not None and stop.is_set():
            raise LintStoppedError
