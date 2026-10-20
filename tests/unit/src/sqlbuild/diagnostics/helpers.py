import logging
import threading


class HostRecordingLogHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []
        self.was_closed: bool = False

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def close(self) -> None:
        self.was_closed = True
        super().close()


def log_vendor_records() -> None:
    """Log like a client library: progress, a recovered failure and an error."""

    logger: logging.Logger = logging.getLogger("vendor.client")
    logger.info("connecting to the orders service")
    try:
        raise RuntimeError("token expired")
    except RuntimeError:
        logger.warning("token refresh failed\nretrying with fallback", exc_info=True)
        logger.error("orders service rejected the request", exc_info=True)


SPINNER_THREAD_NAME: str = "sqlbuild-progress-spinner"


def spinner_threads() -> list[threading.Thread]:
    """The live progress spinner threads."""

    return list(filter(lambda thread: thread.name == SPINNER_THREAD_NAME, threading.enumerate()))


def spinner_threads_started_after(earlier: list[threading.Thread]) -> list[threading.Thread]:
    """The live spinner threads not in `earlier`, ignoring other tests' lingering threads."""

    return list(filter(lambda thread: thread not in earlier, spinner_threads()))


def stopped_after_join(threads: list[threading.Thread], timeout_seconds: float) -> bool:
    """Whether every thread in `threads` has finished within `timeout_seconds` each."""

    list(map(lambda thread: thread.join(timeout=timeout_seconds), threads))
    return not any(map(lambda thread: thread.is_alive(), threads))
