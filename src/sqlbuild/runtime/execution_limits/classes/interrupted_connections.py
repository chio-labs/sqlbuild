"""Connections whose running statement a deadline interrupted, awaiting a health check."""

from __future__ import annotations

import threading
import weakref
from collections.abc import Callable
from typing import Any


class InterruptedConnections:
    """Interrupted connections, held weakly where possible and each cleared when it is checked."""

    def __init__(self) -> None:
        self._connections: dict[int, Callable[[], Any]] = {}
        self._lock: threading.Lock = threading.Lock()

    def mark(self, connection: Any) -> None:
        reference: Callable[[], Any] = _reference(connection)
        with self._lock:
            self._connections[id(connection)] = reference

    def take(self, connection: Any) -> bool:
        """Whether `connection` itself was interrupted since its last check, clearing the mark."""

        with self._lock:
            reference: Callable[[], Any] | None = self._connections.pop(id(connection), None)
        return reference is not None and reference() is connection


def _reference(connection: Any) -> Callable[[], Any]:
    """A weak reference to `connection`, or a strong one when it cannot be weakly referenced."""

    try:
        return weakref.ref(connection)
    except TypeError:
        return lambda: connection
