"""Failure-isolated legacy diagnostic file handler."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path


class SafeDiagnosticFileHandler(logging.FileHandler):
    """Disable a failed file route and report its first failure without recursion."""

    def __init__(
        self,
        *,
        filename: Path,
        mode: str,
        encoding: str,
        failure_callback: Callable[[Exception], None],
    ) -> None:
        super().__init__(filename=filename, mode=mode, encoding=encoding)
        self._failure_callback: Callable[[Exception], None] = failure_callback
        self._failed: bool = False

    def emit(self, record: logging.LogRecord) -> None:
        if not self._failed:
            super().emit(record)

    def handleError(self, record: logging.LogRecord) -> None:
        """Report only the first destination error and suppress logging's stderr traceback."""

        _ = record
        self._failed = True
        error: BaseException | None = sys.exception()
        if isinstance(error, Exception):
            try:
                self._failure_callback(error)
            except Exception:
                pass
