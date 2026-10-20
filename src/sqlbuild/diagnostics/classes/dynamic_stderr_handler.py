"""Dynamic stderr logging handler."""

from __future__ import annotations

import logging
import sys

from sqlbuild._native import shared_transient_line_coordinator


class DynamicStderrHandler(logging.StreamHandler):
    """Stream handler that follows the current stderr and keeps clear of live progress lines."""

    def emit(self, record: logging.LogRecord) -> None:
        self.stream = sys.stderr
        try:
            text: str = self.format(record) + self.terminator
            shared_transient_line_coordinator().write_persistent(stream=self.stream, text=text)
        except RecursionError:
            raise
        except Exception:
            self.handleError(record)

    def handleError(self, record: logging.LogRecord) -> None:
        """Isolate console failures from the command and avoid recursive fallback logging."""

        _ = record
