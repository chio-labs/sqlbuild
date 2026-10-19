"""Compute log storage never runs Python while holding its lock, so it cannot deadlock on the GIL."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

from tests.integration.src.sqlbuild.runtime.compute_logs._test_types import (
    StorageLockTestCase,
)

_DEADLOCK_TIMEOUT_SECONDS: int = 30

# A late write from a background thread reaches a capture that was already marked complete.
# Raising its rejection imports the storage exceptions, here forced to load afresh, and the
# import's file system calls release the GIL. The finder below holds that import open until the main thread is
# pruning, which takes the storage lock while holding the GIL.
_LATE_APPEND_DURING_PRUNE: str = dedent(
    """
    import dataclasses
    import sys
    import threading
    import time
    from datetime import UTC, datetime
    from pathlib import Path

    from sqlbuild.compute_logs import (
        COMPUTE_LOG_FORMAT_VERSION,
        CaptureMetadata,
        ComputeLogStream,
        FinalCaptureMetadata,
        LocalFilesystemComputeLogStorage,
    )

    EXCEPTIONS_MODULE = "sqlbuild.runtime.compute_logs.exceptions"
    importing = threading.Event()


    class SlowExceptionsImport:
        def find_spec(self, name, path=None, target=None):
            if name == EXCEPTIONS_MODULE and not importing.is_set():
                importing.set()
                time.sleep(0.5)
            return None


    project_dir = Path(sys.argv[1])
    started_at = datetime.now(UTC)
    metadata = CaptureMetadata(
        format_version=COMPUTE_LOG_FORMAT_VERSION,
        invocation_id="orders0000000000000000000000000a",
        command="compile",
        project_dir=str(project_dir),
        started_at=started_at,
        capture_date=started_at.date().isoformat(),
    )
    storage = LocalFilesystemComputeLogStorage(project_dir=project_dir)
    storage.start_capture(metadata)
    storage.mark_complete(
        FinalCaptureMetadata(
            **dataclasses.asdict(metadata),
            completed_at=datetime.now(UTC),
            exit_code=1,
            stdout_bytes=0,
            stderr_bytes=0,
            diagnostics_bytes=0,
        )
    )
    rejected = []
    del sys.modules[EXCEPTIONS_MODULE]
    sys.meta_path.insert(0, SlowExceptionsImport())


    def late_append():
        try:
            storage.append(
                invocation_id=metadata.invocation_id,
                stream=ComputeLogStream.STDERR,
                data=b"late customer export notice\\n",
            )
        except Exception as error:
            rejected.append(type(error).__name__)


    writer = threading.Thread(target=late_append)
    writer.start()
    importing.wait()
    storage.prune()
    writer.join()
    print(rejected)
    """
)


@pytest.mark.parametrize(
    "test_case",
    (
        StorageLockTestCase(
            description="late append rejected while the main thread prunes",
            script=_LATE_APPEND_DURING_PRUNE,
            expected_stdout="['CaptureStateError']\n",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_rejected_append_releasing_gil_when_pruning_then_both_threads_finish(
    test_case: StorageLockTestCase, tmp_path: Path
) -> None:
    try:
        completed: subprocess.CompletedProcess[str] = subprocess.run(
            [sys.executable, "-c", test_case.script, str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=_DEADLOCK_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"storage calls deadlocked for {_DEADLOCK_TIMEOUT_SECONDS}s")

    assert (completed.returncode, completed.stdout) == (0, test_case.expected_stdout), (
        completed.stderr
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
