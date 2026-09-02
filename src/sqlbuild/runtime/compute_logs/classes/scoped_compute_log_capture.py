"""Scoped process stream and diagnostic compute capture."""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

from sqlbuild.diagnostics.classes.invocation_diagnostic_routing import InvocationDiagnosticRouting
from sqlbuild.diagnostics.models import DiagnosticRoutingOptions
from sqlbuild.runtime.compute_logs.classes.local_filesystem_compute_log_storage import (
    LocalFilesystemComputeLogStorage,
)
from sqlbuild.runtime.compute_logs.classes.text_tee import TextComputeLogTee
from sqlbuild.runtime.compute_logs.models import (
    CaptureByteCounts,
    CaptureMetadata,
    FinalCaptureMetadata,
)
from sqlbuild.runtime.compute_logs.types import ComputeLogStream


class ScopedComputeLogCapture:
    """Own scoped process capture while preserving the wrapped operation outcome."""

    def __init__(
        self,
        *,
        storage: LocalFilesystemComputeLogStorage,
        metadata: CaptureMetadata,
        failure_callback: Callable[[Exception, str], None],
        routing_options: DiagnosticRoutingOptions | None = None,
    ) -> None:
        self._storage: LocalFilesystemComputeLogStorage = storage
        self._metadata: CaptureMetadata = metadata
        self._failure_callback: Callable[[Exception, str], None] = failure_callback
        self._original_stdout: Any = sys.stdout
        self._original_stderr: Any = sys.stderr
        self._routing_options: DiagnosticRoutingOptions = (
            DiagnosticRoutingOptions() if routing_options is None else routing_options
        )
        self._stdout_tee: TextComputeLogTee | None = None
        self._stderr_tee: TextComputeLogTee | None = None
        self._routing: InvocationDiagnosticRouting | None = None

    def run(self, *, operation: Callable[[], int]) -> int:
        """Install capture, run once, clean up, and restore the original outcome."""

        try:
            self._install()
        except Exception as setup_error:
            _ = self._cleanup()
            self._close_storage()
            self._report(error=setup_error, channel="capture_setup")
            return operation()
        operation_result: int = 1
        operation_error: BaseException | None = None
        try:
            operation_result = operation()
        except BaseException as error:
            operation_error = error
            if isinstance(error, SystemExit) and isinstance(error.code, int):
                operation_result = error.code
        cleanup_succeeded: bool = self._cleanup()
        if cleanup_succeeded:
            self._finalize(exit_code=operation_result)
        else:
            self._close_storage()
        if operation_error is not None:
            raise operation_error.with_traceback(operation_error.__traceback__)
        return operation_result

    def _install(self) -> None:
        write_failure: Callable[[Exception], None] = partial(self._report, channel="capture_write")
        self._stdout_tee = TextComputeLogTee(
            sink=self._original_stdout,
            storage=self._storage,
            invocation_id=self._metadata.invocation_id,
            stream=ComputeLogStream.STDOUT,
            failure_callback=write_failure,
        )
        self._stderr_tee = TextComputeLogTee(
            sink=self._original_stderr,
            storage=self._storage,
            invocation_id=self._metadata.invocation_id,
            stream=ComputeLogStream.STDERR,
            failure_callback=write_failure,
        )
        self._routing = InvocationDiagnosticRouting(
            target_dir=Path(self._metadata.project_dir) / "target",
            storage=self._storage,
            invocation_id=self._metadata.invocation_id,
            options=self._routing_options,
            failure_callback=write_failure,
        )
        self._routing.__enter__()
        sys.stdout = self._stdout_tee
        sys.stderr = self._stderr_tee

    def _cleanup(self) -> bool:
        cleanup_succeeded: bool = True
        for tee in (self._stdout_tee, self._stderr_tee):
            if tee is None:
                continue
            try:
                tee.flush()
            except Exception as error:
                cleanup_succeeded = False
                self._report(error=error, channel="capture_flush")
        sys.stdout = self._original_stdout
        sys.stderr = self._original_stderr
        if self._routing is not None:
            try:
                self._routing.__exit__(None, None, None)
            except Exception as error:
                cleanup_succeeded = False
                self._report(error=error, channel="capture_cleanup")
        return cleanup_succeeded

    def _finalize(self, *, exit_code: int) -> None:
        try:
            counts: CaptureByteCounts = self._storage.get_byte_counts(
                invocation_id=self._metadata.invocation_id
            )
            final_metadata: FinalCaptureMetadata = FinalCaptureMetadata(
                format_version=self._metadata.format_version,
                invocation_id=self._metadata.invocation_id,
                command=self._metadata.command,
                project_dir=self._metadata.project_dir,
                started_at=self._metadata.started_at,
                capture_date=self._metadata.capture_date,
                completed_at=datetime.now(UTC),
                exit_code=exit_code,
                stdout_bytes=counts.stdout_bytes,
                stderr_bytes=counts.stderr_bytes,
                diagnostics_bytes=counts.diagnostics_bytes,
                target=self._metadata.target,
                run_id=self._metadata.run_id,
            )
            self._storage.mark_complete(final_metadata)
            _ = self._storage.prune()
        except Exception as error:
            self._report(error=error, channel="capture_finalize")
        finally:
            self._close_storage()

    def _close_storage(self) -> None:
        try:
            self._storage.close()
        except Exception as error:
            self._report(error=error, channel="capture_close")

    def _report(self, *, error: Exception, channel: str) -> None:
        try:
            self._failure_callback(error, channel)
        except Exception as callback_error:
            _ = callback_error
