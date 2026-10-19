"""Open Recall store connections, kept in Python and named to native code by integer handles."""

from __future__ import annotations

import itertools
import threading
from collections.abc import Iterator

from sqlbuild.adapters.clickhouse.classes.clickhouse_connection import _ClickHouseConnection


class RecallConnections:
    """Hand out a handle per open connection and look connections up by handle."""

    def __init__(self) -> None:
        self._guard: threading.Lock = threading.Lock()
        self._handles: Iterator[int] = itertools.count(1)
        self._connections: dict[int, _ClickHouseConnection] = {}

    def add(self, *, connection: _ClickHouseConnection) -> int:
        """Keep ``connection`` and return its new handle."""

        with self._guard:
            handle: int = next(self._handles)
            self._connections[handle] = connection
        return handle

    def get(self, *, handle: int) -> _ClickHouseConnection:
        """The connection ``handle`` names."""

        return self._connections[handle]

    def pop(self, *, handle: int) -> _ClickHouseConnection | None:
        """Forget ``handle`` and return its connection, if it is still open."""

        with self._guard:
            return self._connections.pop(handle, None)
