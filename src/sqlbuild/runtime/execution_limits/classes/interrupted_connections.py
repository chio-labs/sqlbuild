"""Connections whose running statement a deadline interrupted, awaiting a health check."""

from __future__ import annotations

import threading
from typing import Any


class InterruptedConnections:
    """Identities of interrupted connections, each cleared when it is checked."""

    def __init__(self) -> None:
        self._connections: set[int] = set()
        self._lock: threading.Lock = threading.Lock()

    def mark(self, connection: Any) -> None:
        with self._lock:
            self._connections.add(id(connection))

    def take(self, connection: Any) -> bool:
        """Whether `connection` was interrupted since it was last checked, clearing the mark."""

        with self._lock:
            interrupted: bool = id(connection) in self._connections
            self._connections.discard(id(connection))
            return interrupted
