"""Process-wide ordering of background fact publications per cache database."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path


class FactPublicationRegistry:
    """Serialize publications per database and let readers wait for pending writes."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._writers: dict[Path, threading.Thread] = {}

    def start(
        self,
        *,
        database_path: Path,
        write: Callable[[threading.Thread | None], None],
        thread_name: str,
    ) -> None:
        """Start one writer that first waits for the previous writer of the same database."""

        with self._lock:
            previous: threading.Thread | None = self._writers.get(database_path)
            writer: threading.Thread = threading.Thread(
                target=write, args=(previous,), name=thread_name
            )
            self._writers[database_path] = writer
            writer.start()

    def wait(self, *, database_path: Path | None) -> None:
        """Wait for the latest writer of one database, or of every database when None."""

        with self._lock:
            writers: tuple[threading.Thread, ...] = tuple(
                writer
                for path, writer in self._writers.items()
                if database_path is None or path == database_path
            )
        for writer in writers:
            writer.join()
