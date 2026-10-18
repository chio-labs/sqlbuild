"""Check connections a deadline interrupted before reuse, replacing those left unusable."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from sqlbuild.runtime.execution_limits._helpers.interrupted import interrupted_connections
from sqlbuild.runtime.execution_limits.constants import CONNECTION_PROBE_SQL
from sqlbuild.runtime.execution_limits.main.execution_deadlines_suspended import (
    execution_deadlines_suspended,
)

_LOGGER: logging.Logger = logging.getLogger("sqlbuild.execution")


class ConnectionRecovery:
    """Probe each interrupted connection, roll it back if needed, and replace it if still broken."""

    def __init__(self, *, adapter: Any, connect: Callable[[], Any]) -> None:
        self._adapter: Any = adapter
        self._connect: Callable[[], Any] = connect
        self._replacements: list[Any] = []
        self._broken: set[int] = set()
        self._lock: threading.Lock = threading.Lock()

    def usable(self, connection: Any) -> Any:
        """`connection` if healthy, else a replacement, else the original kept marked broken."""

        interrupted: bool = interrupted_connections.take(connection)
        with self._lock:
            broken: bool = id(connection) in self._broken
        if not interrupted and not broken:
            return connection
        with execution_deadlines_suspended():
            if self._responds(connection):
                self._forget_broken(connection)
                return connection
            try:
                self._adapter.rollback(connection)
            except Exception as error:
                _LOGGER.debug("rollback after an interrupted statement failed: %s", error)
            if self._responds(connection):
                self._forget_broken(connection)
                return connection
        try:
            replacement: Any = self._connect()
        except Exception as error:
            with self._lock:
                self._broken.add(id(connection))
            _LOGGER.warning(
                "A connection left unusable by a timed-out statement could not be replaced (%s); "
                "work that uses it will fail",
                error,
            )
            return connection
        _LOGGER.warning("A connection left unusable by a timed-out statement was replaced")
        self._forget_broken(connection)
        with self._lock:
            self._replacements.append(replacement)
        return replacement

    def close_replacements(self) -> None:
        """Close the connections this recovery opened; the originals are closed by their owner."""

        with self._lock:
            replacements: list[Any] = list(self._replacements)
            self._replacements.clear()
        for replacement in replacements:
            try:
                self._adapter.close(replacement)
            except Exception as error:
                _LOGGER.debug("closing a replacement connection failed: %s", error)

    def _forget_broken(self, connection: Any) -> None:
        with self._lock:
            self._broken.discard(id(connection))

    def _responds(self, connection: Any) -> bool:
        try:
            _ = self._adapter.execute(connection=connection, sql=CONNECTION_PROBE_SQL)
        except Exception as error:
            _LOGGER.debug("connection probe after an interrupted statement failed: %s", error)
            return False
        return True
