"""In-process locks that serialize rewrites of one ClickHouse partition."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager


class PartitionLocks:
    """Hand out one lock per destination partition and acquire them in a deadlock-free order."""

    def __init__(self) -> None:
        self._guard: threading.Lock = threading.Lock()
        self._locks: dict[tuple[str, str], threading.Lock] = {}

    @contextmanager
    def locked(self, *, destination: str, partitions: tuple[str, ...]) -> Iterator[None]:
        """Hold the locks of sorted ``partitions`` of ``destination`` while the body runs."""

        with self._guard:
            locks: list[threading.Lock] = [
                self._locks.setdefault((destination, partition), threading.Lock())
                for partition in partitions
            ]
        acquired: list[threading.Lock] = []
        try:
            lock: threading.Lock
            for lock in locks:
                lock.acquire()
                acquired.append(lock)
            yield
        finally:
            for lock in reversed(acquired):
                lock.release()
