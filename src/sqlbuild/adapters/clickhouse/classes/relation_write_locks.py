"""In-process shared and exclusive locks on whole ClickHouse relations."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager


class RelationWriteLocks:
    """Let partition swaps share a relation while a whole-table exchange holds it alone."""

    def __init__(self) -> None:
        self._condition: threading.Condition = threading.Condition()
        self._sharers: dict[str, int] = {}
        self._exclusive: set[str] = set()

    @contextmanager
    def shared(self, *, destination: str) -> Iterator[None]:
        """Hold ``destination`` alongside other sharers while no exchange holds it."""

        with self._condition:
            self._condition.wait_for(lambda: destination not in self._exclusive)
            self._sharers[destination] = self._sharers.get(destination, 0) + 1
        try:
            yield
        finally:
            with self._condition:
                self._sharers[destination] -= 1
                self._condition.notify_all()

    @contextmanager
    def exclusive(self, *, destination: str) -> Iterator[None]:
        """Hold ``destination`` alone, after current sharers and exchanges finish."""

        with self._condition:
            self._condition.wait_for(
                lambda: (
                    destination not in self._exclusive and self._sharers.get(destination, 0) == 0
                )
            )
            self._exclusive.add(destination)
        try:
            yield
        finally:
            with self._condition:
                self._exclusive.discard(destination)
                self._condition.notify_all()
