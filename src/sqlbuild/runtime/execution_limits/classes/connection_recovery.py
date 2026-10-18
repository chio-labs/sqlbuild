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
        self._lock: threading.Lock = threading.Lock()

    def usable(self, connection: Any) -> Any:
        """`connection` when it is healthy, otherwise a newly opened replacement."""

        if not interrupted_connections.take(connection):
            return connection
        with execution_deadlines_suspended():
            if self._responds(connection):
                return connection
            try:
                self._adapter.rollback(connection)
            except Exception as error:
                _LOGGER.debug("rollback after an interrupted statement failed: %s", error)
            if self._responds(connection):
                return connection
        _LOGGER.warning("A connection left unusable by a timed-out statement was replaced")
        replacement: Any = self._connect()
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

    def _responds(self, connection: Any) -> bool:
        try:
            _ = self._adapter.execute(connection=connection, sql=CONNECTION_PROBE_SQL)
        except Exception as error:
            _LOGGER.debug("connection probe after an interrupted statement failed: %s", error)
            return False
        return True
