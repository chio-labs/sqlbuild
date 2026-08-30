"""Thread-safe JSON Lines execution event writer."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import TextIO

from sqlbuild.cli.output.constants import EXECUTION_EVENT_PATH_ENV


class ExecutionEventWriter:
    """Append and flush structured execution events for a parent integration."""

    def __init__(self, *, path: Path | None = None) -> None:
        configured_path: str | None = os.environ.get(EXECUTION_EVENT_PATH_ENV)
        self._path: Path | None = path or (Path(configured_path) if configured_path else None)
        self._stream: TextIO | None = None
        self._lock: threading.Lock = threading.Lock()
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._stream = self._path.open(mode="a", encoding="utf-8")

    def write(self, payload: str | None) -> None:
        """Write and flush one or more complete JSON Lines records."""

        if self._stream is None or payload is None:
            return
        with self._lock:
            self._stream.write(payload)
            self._stream.flush()

    def close(self) -> None:
        """Close the event stream when configured."""

        if self._stream is not None:
            self._stream.close()
            self._stream = None
