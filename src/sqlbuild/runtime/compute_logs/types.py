"""Compute log stream declarations and storage protocol."""

from __future__ import annotations

from enum import StrEnum
from types import TracebackType
from typing import TYPE_CHECKING, Protocol, Self

from sqlbuild.runtime.compute_logs.constants import MAX_READ_BYTES

if TYPE_CHECKING:
    from sqlbuild.runtime.compute_logs.models import (
        CaptureByteCounts,
        CaptureInventory,
        CaptureMetadata,
        ComputeLogReadChunk,
        FinalCaptureMetadata,
        PruneResult,
    )
    from sqlbuild.runtime.observability.models import DiagnosticLog

type ByteCursor = int


class ComputeLogStream(StrEnum):
    """Independent byte streams retained for one invocation."""

    STDOUT = "stdout"
    STDERR = "stderr"
    DIAGNOSTICS = "diagnostics"


class ComputeLogStorage(Protocol):
    """Backend-neutral raw invocation log storage."""

    def start_capture(self, metadata: CaptureMetadata) -> None: ...

    def append(self, *, invocation_id: str, stream: ComputeLogStream, data: bytes) -> None: ...

    def append_diagnostic(self, *, invocation_id: str, record: DiagnosticLog) -> None: ...

    def read(
        self,
        *,
        invocation_id: str,
        stream: ComputeLogStream,
        cursor: ByteCursor = 0,
        max_bytes: int = MAX_READ_BYTES,
    ) -> ComputeLogReadChunk: ...

    def get_metadata(self, *, invocation_id: str) -> CaptureMetadata | FinalCaptureMetadata: ...

    def get_byte_count(self, *, invocation_id: str, stream: ComputeLogStream) -> int: ...

    def get_byte_counts(self, *, invocation_id: str) -> CaptureByteCounts: ...

    def is_complete(self, *, invocation_id: str) -> bool: ...

    def mark_complete(self, metadata: FinalCaptureMetadata) -> None: ...

    def delete(self, *, invocation_id: str) -> None: ...

    def prune(self, retain_count: int | None = None) -> PruneResult: ...

    def inventory(self) -> CaptureInventory: ...

    def close(self) -> None: ...

    def dispose(self) -> None: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None: ...
