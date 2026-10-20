import logging


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
