"""Ctrl-C state shared by the scenario scheduler and running scenarios."""

from __future__ import annotations

import signal
import sys
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlbuild.presentation.main.transient_line_coordinator import (
    shared_transient_line_coordinator,
)

_STOP_NOTICE: str = "Interrupted; cleaning up running scenarios...\n"
_ABANDON_NOTICE: str = (
    "Interrupted again; skipped scenario cleanup. Leftover scenario relations are dropped "
    "the next time those scenarios run.\n"
)


class ScenarioInterrupts:
    """First Ctrl-C stops scenarios and cleans up; a repeat abandons cleanup and exits."""

    def __init__(self, *, cancel_statements: Callable[[], None] | None = None) -> None:
        self._cancel_statements: Callable[[], None] | None = cancel_statements
        self.stop_requested: threading.Event = threading.Event()
        self.abandoned: threading.Event = threading.Event()
        self._lock: threading.Lock = threading.Lock()
        self._announced: set[str] = set()

    @contextmanager
    def handle_sigint(self) -> Iterator[None]:
        """Record Ctrl-C and cancel in-flight statements, even when a driver hides the signal."""

        if threading.current_thread() is not threading.main_thread():
            yield
            return
        previous: object = signal.getsignal(signal.SIGINT)
        if previous is not signal.default_int_handler:
            yield
            return
        _ = signal.signal(signal.SIGINT, self._on_sigint)
        try:
            yield
        finally:
            _ = signal.signal(signal.SIGINT, previous)

    def request_stop(self) -> None:
        """Ask running scenarios to stop at their next step."""

        self.stop_requested.set()

    def abandon(self) -> None:
        """Skip all remaining cleanup and tell the user once."""

        self.abandoned.set()
        self._announce(_ABANDON_NOTICE)

    def announce_stop(self) -> None:
        """Tell the user, once, that scenarios are stopping and cleaning up."""

        self._announce(_STOP_NOTICE)

    def _announce(self, notice: str) -> None:
        with self._lock:
            if notice in self._announced:
                return
            self._announced.add(notice)
        shared_transient_line_coordinator().write_persistent(stream=sys.stderr, text=notice)

    def _on_sigint(self, *_signal_args: object) -> None:
        if self.stop_requested.is_set():
            self.abandoned.set()
        self.stop_requested.set()
        if self._cancel_statements is not None:
            self._cancel_statements()
        raise KeyboardInterrupt
