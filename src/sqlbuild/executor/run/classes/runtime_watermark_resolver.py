"""Run-scoped concurrency-safe watermark resolution."""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future


class RuntimeWatermarkResolver:
    """Cache successful and failed physical watermark reads for one build run."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._futures: dict[tuple[str, str, bool], Future[tuple[object | None, object | None]]] = {}

    def resolve(
        self,
        *,
        relation: str,
        cursor_column: str,
        read_minimum: bool,
        query: Callable[[], tuple[object | None, object | None]],
    ) -> tuple[object | None, object | None]:
        """Resolve an exact bound shape once and share its result or failure."""

        key: tuple[str, str, bool] = (relation, cursor_column, read_minimum)
        owns_query: bool = False
        with self._lock:
            future: Future[tuple[object | None, object | None]] | None = self._futures.get(key)
            if future is None:
                future = Future()
                self._futures[key] = future
                owns_query = True
        if not owns_query:
            return future.result()
        try:
            result: tuple[object | None, object | None] = query()
        except BaseException as error:
            future.set_exception(error)
            raise
        future.set_result(result)
        return result
