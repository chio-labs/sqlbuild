"""Typed public compute log storage API."""

from pathlib import Path

from sqlbuild.runtime.compute_logs.classes.local_filesystem_compute_log_storage import (
    LocalFilesystemComputeLogStorage,
)
from sqlbuild.runtime.compute_logs.constants import (
    COMPUTE_LOG_FORMAT_VERSION,
    DEFAULT_RETENTION_COUNT,
    MAX_READ_BYTES,
)
from sqlbuild.runtime.compute_logs.exceptions import (
    CaptureAlreadyExistsError,
    CaptureNotFoundError,
    CaptureStateError,
    ComputeLogMetadataError,
    ComputeLogPathError,
    ComputeLogStorageError,
    InvalidCaptureIdError,
    InvalidComputeLogCursorError,
    InvalidComputeLogLimitError,
)
from sqlbuild.runtime.compute_logs.main.open_local_compute_log_storage import (
    open_local_compute_log_storage as _open_local_compute_log_storage,
)
from sqlbuild.runtime.compute_logs.models import (
    CaptureByteCounts,
    CaptureInventory,
    CaptureInventoryItem,
    CaptureMetadata,
    ComputeLogReadChunk,
    FinalCaptureMetadata,
    PruneResult,
    StreamByteCount,
)
from sqlbuild.runtime.compute_logs.types import ByteCursor, ComputeLogStorage, ComputeLogStream

__all__ = (
    "COMPUTE_LOG_FORMAT_VERSION",
    "DEFAULT_RETENTION_COUNT",
    "MAX_READ_BYTES",
    "ByteCursor",
    "CaptureAlreadyExistsError",
    "CaptureByteCounts",
    "CaptureInventory",
    "CaptureInventoryItem",
    "CaptureMetadata",
    "CaptureNotFoundError",
    "CaptureStateError",
    "ComputeLogMetadataError",
    "ComputeLogPathError",
    "ComputeLogReadChunk",
    "ComputeLogStorage",
    "ComputeLogStorageError",
    "ComputeLogStream",
    "FinalCaptureMetadata",
    "InvalidCaptureIdError",
    "InvalidComputeLogCursorError",
    "InvalidComputeLogLimitError",
    "LocalFilesystemComputeLogStorage",
    "PruneResult",
    "StreamByteCount",
    "open_local_compute_log_storage",
)


def open_local_compute_log_storage(
    *,
    project_dir: Path,
    root: Path | None = None,
    retention_count: int | None = DEFAULT_RETENTION_COUNT,
) -> LocalFilesystemComputeLogStorage:
    """Open the supported project-local backend, defaulting to project logs."""

    return _open_local_compute_log_storage(
        project_dir=project_dir,
        root=root,
        retention_count=retention_count,
    )
