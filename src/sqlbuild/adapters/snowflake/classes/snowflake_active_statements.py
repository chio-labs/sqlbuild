"""The Snowflake statements one connection is running, so a deadline can cancel them."""

from __future__ import annotations

import threading
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlbuild.adapters.snowflake.exceptions import SnowflakeCancellationError


class SnowflakeActiveStatements:
    """Running cursors of one connection, with the SQL each submitted."""

    def __init__(self) -> None:
        self._running: dict[int, tuple[Any, str]] = {}
        self._lock: threading.Lock = threading.Lock()

    @contextmanager
    def running(self, *, raw_cursor: Any, sql: str) -> Generator[None]:
        """Record `sql` running on `raw_cursor` for the duration of the block."""

        with self._lock:
            self._running[id(raw_cursor)] = (raw_cursor, sql)
        try:
            yield
        finally:
            with self._lock:
                _ = self._running.pop(id(raw_cursor), None)

    def cancel(self, *, raw_connection: Any) -> None:
        """Ask Snowflake to abort every running statement; raise if it refuses."""

        with self._lock:
            running: list[tuple[Any, str]] = list(self._running.values())
        for raw_cursor, sql in running:
            request_id: object | None = getattr(raw_cursor, "_request_id", None)
            if request_id is None:
                continue
            response: object = raw_connection._cancel_query(sql, request_id)
            if isinstance(response, dict) and response.get("success") is False:
                raise SnowflakeCancellationError(
                    request_id=request_id, message=response.get("message")
                )
