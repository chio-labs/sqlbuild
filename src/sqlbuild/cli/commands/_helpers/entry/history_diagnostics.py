"""Best-effort diagnostics for local execution history degradation."""

import logging

from sqlbuild.diagnostics.main.log_debug_event import log_debug_event
from sqlbuild.observability import DispatchFailure

_LOGGER: logging.Logger = logging.getLogger("sqlbuild.cli.execution_history")


def log_history_open_failure(*, error: Exception) -> None:
    """Report local history setup degradation without affecting command behavior."""

    try:
        log_debug_event(
            logger=_LOGGER,
            message="local execution history unavailable",
            error_type=type(error).__name__,
            channel="history_open",
            subscriber="SQLiteExecutionHistory",
        )
    except Exception:
        pass


def log_history_dispatch_failure(failure: DispatchFailure) -> None:
    """Report an isolated lifecycle persistence subscriber failure."""

    log_debug_event(
        logger=_LOGGER,
        message="local execution history persistence failed",
        error_type=failure.error_type,
        channel=failure.channel,
        subscriber=failure.subscriber,
    )
