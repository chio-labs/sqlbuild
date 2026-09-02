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
