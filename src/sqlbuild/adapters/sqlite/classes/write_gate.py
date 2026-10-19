"""One SQLite writer per database file per process."""

from __future__ import annotations

import threading

from sqlbuild.adapters.sqlite.constants import WRITE_GATE_POLL_SECONDS
from sqlbuild.runtime.execution_limits.main.enforce_execution_deadline import (
    enforce_execution_deadline,
)


class WriteGate:
    """Queue a process's writers; a thread already writing through another connection passes."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._owner: int | None = None

    def acquire(self) -> bool:
        """Wait for the gate, honouring deadlines; False when this thread already holds it."""

        if self._owner == threading.get_ident():
            return False
        while not self._lock.acquire(timeout=WRITE_GATE_POLL_SECONDS):
            enforce_execution_deadline()
        self._owner = threading.get_ident()
        return True

    def release(self) -> None:
        self._owner = None
        self._lock.release()
