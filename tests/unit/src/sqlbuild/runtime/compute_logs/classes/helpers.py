from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

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


class InvalidLogMessage:
    def __str__(self) -> str:
        raise ValueError("controlled invalid message")


class FailOnceBinaryWriter:
    def __init__(self, writer: BinaryIO) -> None:
        self._writer: BinaryIO = writer
        self.close_calls: int = 0
        self._close_actions: Iterator[Callable[[], None]] = iter(
            (self._fail_first_close, writer.close)
        )

    def close(self) -> None:
        self.close_calls += 1
        next(self._close_actions)()

    @property
    def closed(self) -> bool:
        return self._writer.closed

    def __getattr__(self, name: str) -> Any:
        return getattr(self._writer, name)

    @staticmethod
    def _fail_first_close() -> None:
        raise OSError("controlled first close failure")


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
