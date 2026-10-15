"""Run one operation with its process streams and diagnostics captured."""

from collections.abc import Callable

from sqlbuild._native import LocalFilesystemComputeLogStorage
from sqlbuild.diagnostics.models import DiagnosticRoutingOptions
from sqlbuild.runtime.compute_logs.classes.scoped_compute_log_capture import (
    ScopedComputeLogCapture,
)
from sqlbuild.runtime.compute_logs.models import CaptureMetadata


def run_with_compute_log_capture(
    *,
    storage: LocalFilesystemComputeLogStorage,
    metadata: CaptureMetadata,
    failure_callback: Callable[[Exception, str], None],
    routing_options: DiagnosticRoutingOptions,
    operation: Callable[[], int],
) -> int:
    """Capture streams and diagnostics around `operation`, preserving its outcome."""

    capture: ScopedComputeLogCapture = ScopedComputeLogCapture(
        storage=storage,
        metadata=metadata,
        failure_callback=failure_callback,
        routing_options=routing_options,
    )
    return capture.run(operation=operation)
