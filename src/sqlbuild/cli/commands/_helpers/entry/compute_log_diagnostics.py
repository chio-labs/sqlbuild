"""Best-effort diagnostics for local compute log degradation."""

import logging

from sqlbuild.diagnostics.main.log_debug_event import log_debug_event

_LOGGER: logging.Logger = logging.getLogger("sqlbuild.cli.compute_logs")


def log_compute_capture_failure(*, error: Exception, channel: str) -> None:
    """Report one bounded capture failure without changing command behavior."""

    try:
        log_debug_event(
            logger=_LOGGER,
            message="local compute log capture unavailable",
            error_type=type(error).__name__,
            channel=channel,
            subscriber="LocalFilesystemComputeLogStorage",
        )
    except Exception:
        pass
