import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlbuild.compute_logs import (
    COMPUTE_LOG_FORMAT_VERSION,
    CaptureMetadata,
    ComputeLogStream,
    FinalCaptureMetadata,
    LocalFilesystemComputeLogStorage,
)


class AccessFailureTextSink:
    encoding: str = "utf-8"
    errors: str = "strict"

    @property
    def buffer(self) -> object:
        raise OSError("controlled buffer access failure")

    def write(self, text: str) -> int:
        return len(text)

    def flush(self) -> None:
        return None


class PatchableComputeLogStorage(LocalFilesystemComputeLogStorage):
    """Native storage whose instance methods tests may replace."""


class InvalidLogMessage:
    def __str__(self) -> str:
        raise ValueError("controlled invalid message")


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


def build_capture_metadata(
    *, project_dir: Path, invocation_id: str, started_at: datetime
) -> CaptureMetadata:
    return CaptureMetadata(
        format_version=COMPUTE_LOG_FORMAT_VERSION,
        invocation_id=invocation_id,
        command="compile",
        project_dir=str(project_dir),
        started_at=started_at,
        capture_date=started_at.astimezone(UTC).date().isoformat(),
    )


def build_final_metadata(
    *,
    storage: LocalFilesystemComputeLogStorage,
    initial: CaptureMetadata,
    completed_at: datetime,
    exit_code: int = 0,
) -> FinalCaptureMetadata:
    return FinalCaptureMetadata(
        format_version=initial.format_version,
        invocation_id=initial.invocation_id,
        command=initial.command,
        project_dir=initial.project_dir,
        started_at=initial.started_at,
        capture_date=initial.capture_date,
        completed_at=completed_at,
        exit_code=exit_code,
        stdout_bytes=storage.get_byte_count(
            invocation_id=initial.invocation_id, stream=ComputeLogStream.STDOUT
        ),
        stderr_bytes=storage.get_byte_count(
            invocation_id=initial.invocation_id, stream=ComputeLogStream.STDERR
        ),
        diagnostics_bytes=storage.get_byte_count(
            invocation_id=initial.invocation_id,
            stream=ComputeLogStream.DIAGNOSTICS,
        ),
    )
