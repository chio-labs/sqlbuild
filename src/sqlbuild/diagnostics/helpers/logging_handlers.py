"""Diagnostics logging handlers."""

from __future__ import annotations

import logging
import sys


class DynamicStderrHandler(logging.StreamHandler):
    """Stream handler that follows the current stderr object at emit time."""

    def emit(self, record: logging.LogRecord) -> None:
        self.stream = sys.stderr
        super().emit(record)
