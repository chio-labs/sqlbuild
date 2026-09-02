"""Local compute log storage construction entrypoint."""

from pathlib import Path

from sqlbuild.runtime.compute_logs.classes.local_filesystem_compute_log_storage import (
    LocalFilesystemComputeLogStorage,
)
from sqlbuild.runtime.compute_logs.constants import DEFAULT_RETENTION_COUNT


def open_local_compute_log_storage(
    *,
    project_dir: Path,
    root: Path | None = None,
    retention_count: int | None = DEFAULT_RETENTION_COUNT,
) -> LocalFilesystemComputeLogStorage:
    """Open the supported project-local compute log backend."""

    return LocalFilesystemComputeLogStorage(
        project_dir=project_dir,
        root=root,
        retention_count=retention_count,
    )
