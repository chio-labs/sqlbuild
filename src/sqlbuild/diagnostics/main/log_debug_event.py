"""Structured debug event entrypoint."""

import logging

from sqlbuild.diagnostics._helpers.logging import log_debug_event as _log_debug_event


def log_debug_event(*, logger: logging.Logger, message: str, **context: object) -> None:
    """Log a structured diagnostics event without SQL."""

    log_result: None = _log_debug_event(logger=logger, message=message, **context)
    return log_result
