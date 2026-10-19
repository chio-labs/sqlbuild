"""Write gates shared by every connection to the same SQLite file."""

from __future__ import annotations

import threading

from sqlbuild.adapters.sqlite.classes.write_gate import WriteGate


class WriteGates:
    """Hand out one gate per database file so all of a process's connections share it."""

    def __init__(self) -> None:
        self._gates: dict[str, WriteGate] = {}
        self._guard: threading.Lock = threading.Lock()

    def for_file(self, key: str) -> WriteGate:
        with self._guard:
            return self._gates.setdefault(key, WriteGate())
