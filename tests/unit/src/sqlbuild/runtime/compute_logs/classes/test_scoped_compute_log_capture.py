import logging
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from unittest.mock import Mock, patch

import pytest

from sqlbuild.compute_logs import (
    CaptureMetadata,
    CaptureStateError,
    ComputeLogStream,
    FinalCaptureMetadata,
)
from sqlbuild.runtime.compute_logs.classes.diagnostic_log_handler import (
    ComputeDiagnosticLogHandler,
)
from sqlbuild.runtime.compute_logs.classes.local_filesystem_compute_log_storage import (
    LocalFilesystemComputeLogStorage,
)
from sqlbuild.runtime.compute_logs.classes.scoped_compute_log_capture import (
    ScopedComputeLogCapture,
)
from sqlbuild.runtime.compute_logs.classes.text_tee import TextComputeLogTee
from tests.unit.src.sqlbuild.runtime.compute_logs.classes._test_types import (
    CaptureOutcomeTestCase,
)
from tests.unit.src.sqlbuild.runtime.compute_logs.classes.helpers import (
    AccessFailureTextSink,
    build_capture_metadata,
)


@pytest.mark.parametrize(
    "test_case",
    (
        CaptureOutcomeTestCase(
            description="buffer access setup failure runs operation without installed capture",
            outcome="return",
            expected_exit_code=7,
            expected_error_type=None,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_tee_setup_failure_when_running_then_operation_and_process_streams_are_preserved(
    tmp_path: Path, test_case: CaptureOutcomeTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage: LocalFilesystemComputeLogStorage = LocalFilesystemComputeLogStorage(
        project_dir=tmp_path
    )
    metadata: CaptureMetadata = build_capture_metadata(
        project_dir=tmp_path, invocation_id="setup_failure", started_at=datetime.now(UTC)
    )
    storage.start_capture(metadata)
    failing_stdout: AccessFailureTextSink = AccessFailureTextSink()
    monkeypatch.setattr(sys, "stdout", failing_stdout)
    handlers_before: tuple[logging.Handler, ...] = tuple(logging.getLogger().handlers)
    operation: Mock = Mock(return_value=test_case.expected_exit_code)
    capture: ScopedComputeLogCapture = ScopedComputeLogCapture(
        storage=storage,
        metadata=metadata,
        failure_callback=lambda _error, _channel: None,
    )

    result: int = capture.run(operation=operation)

    assert result == test_case.expected_exit_code
    assert sys.stdout is failing_stdout
    assert tuple(logging.getLogger().handlers) == handlers_before
    assert storage.is_complete(invocation_id=metadata.invocation_id) is False
    operation.assert_called_once_with()


@pytest.mark.parametrize(
    "test_case",
    (
        CaptureOutcomeTestCase(
            description="sink flush failure preserves return and leaves capture incomplete",
            outcome="return",
            expected_exit_code=8,
            expected_error_type=None,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_sink_flush_failure_when_operation_returns_then_result_and_cleanup_are_preserved(
    tmp_path: Path, test_case: CaptureOutcomeTestCase
) -> None:
    storage: LocalFilesystemComputeLogStorage = LocalFilesystemComputeLogStorage(
        project_dir=tmp_path
    )
    metadata: CaptureMetadata = build_capture_metadata(
        project_dir=tmp_path, invocation_id="flush_failure", started_at=datetime.now(UTC)
    )
    storage.start_capture(metadata)
    original_stdout: object = sys.stdout
    original_stderr: object = sys.stderr
    handlers_before: tuple[logging.Handler, ...] = tuple(logging.getLogger().handlers)
    capture: ScopedComputeLogCapture = ScopedComputeLogCapture(
        storage=storage,
        metadata=metadata,
        failure_callback=lambda _error, _channel: None,
    )

    with patch.object(TextComputeLogTee, "flush", Mock(side_effect=OSError("flush failure"))):
        result: int = capture.run(operation=Mock(return_value=test_case.expected_exit_code))

    assert result == test_case.expected_exit_code
    assert sys.stdout is original_stdout
    assert sys.stderr is original_stderr
    assert tuple(logging.getLogger().handlers) == handlers_before
    assert storage.is_complete(invocation_id=metadata.invocation_id) is False


@pytest.mark.parametrize(
    "test_case",
    (
        CaptureOutcomeTestCase(
            description="handler close failure preserves return and removes handler",
            outcome="return",
            expected_exit_code=6,
            expected_error_type=None,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_handler_close_failure_when_operation_returns_then_handler_does_not_leak(
    tmp_path: Path, test_case: CaptureOutcomeTestCase
) -> None:
    storage: LocalFilesystemComputeLogStorage = LocalFilesystemComputeLogStorage(
        project_dir=tmp_path
    )
    metadata: CaptureMetadata = build_capture_metadata(
        project_dir=tmp_path, invocation_id="handler_failure", started_at=datetime.now(UTC)
    )
    storage.start_capture(metadata)
    handlers_before: tuple[logging.Handler, ...] = tuple(logging.getLogger().handlers)
    capture: ScopedComputeLogCapture = ScopedComputeLogCapture(
        storage=storage,
        metadata=metadata,
        failure_callback=lambda _error, _channel: None,
    )

    with patch.object(
        ComputeDiagnosticLogHandler,
        "close",
        Mock(side_effect=OSError("handler close failure")),
    ):
        result: int = capture.run(operation=Mock(return_value=test_case.expected_exit_code))

    assert result == test_case.expected_exit_code
    assert tuple(logging.getLogger().handlers) == handlers_before
    assert storage.is_complete(invocation_id=metadata.invocation_id) is False


@pytest.mark.parametrize(
    "test_case",
    (
        CaptureOutcomeTestCase(
            description="handler removal failure uses fallback removal without replacing result",
            outcome="return",
            expected_exit_code=4,
            expected_error_type=None,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_handler_removal_failure_when_cleaning_then_fallback_prevents_handler_leak(
    tmp_path: Path, test_case: CaptureOutcomeTestCase
) -> None:
    storage: LocalFilesystemComputeLogStorage = LocalFilesystemComputeLogStorage(
        project_dir=tmp_path
    )
    metadata: CaptureMetadata = build_capture_metadata(
        project_dir=tmp_path, invocation_id="removal_failure", started_at=datetime.now(UTC)
    )
    storage.start_capture(metadata)
    root_logger: logging.Logger = logging.getLogger()
    handlers_before: tuple[logging.Handler, ...] = tuple(root_logger.handlers)
    capture: ScopedComputeLogCapture = ScopedComputeLogCapture(
        storage=storage,
        metadata=metadata,
        failure_callback=lambda _error, _channel: None,
    )

    with patch.object(
        root_logger,
        "removeHandler",
        Mock(side_effect=OSError("handler removal failure")),
    ):
        result: int = capture.run(operation=Mock(return_value=test_case.expected_exit_code))

    assert result == test_case.expected_exit_code
    assert tuple(root_logger.handlers) == handlers_before
    assert storage.is_complete(invocation_id=metadata.invocation_id) is False


@pytest.mark.parametrize(
    "test_case",
    (
        CaptureOutcomeTestCase(
            description="finalization failure preserves operation result",
            outcome="return",
            expected_exit_code=5,
            expected_error_type=None,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_finalization_failure_when_operation_returns_then_result_is_not_replaced(
    tmp_path: Path, test_case: CaptureOutcomeTestCase
) -> None:
    storage: LocalFilesystemComputeLogStorage = LocalFilesystemComputeLogStorage(
        project_dir=tmp_path
    )
    metadata: CaptureMetadata = build_capture_metadata(
        project_dir=tmp_path, invocation_id="finalize_failure", started_at=datetime.now(UTC)
    )
    storage.start_capture(metadata)
    capture: ScopedComputeLogCapture = ScopedComputeLogCapture(
        storage=storage,
        metadata=metadata,
        failure_callback=lambda _error, _channel: None,
    )

    with patch.object(storage, "mark_complete", Mock(side_effect=OSError("finalize failure"))):
        result: int = capture.run(operation=Mock(return_value=test_case.expected_exit_code))

    assert result == test_case.expected_exit_code
    assert storage.is_complete(invocation_id=metadata.invocation_id) is False


@pytest.mark.parametrize(
    "test_case",
    (
        CaptureOutcomeTestCase(
            description="storage close failure after real cleanup does not replace result",
            outcome="return",
            expected_exit_code=3,
            expected_error_type=None,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_storage_close_failure_when_cleanup_runs_then_result_and_writer_cleanup_are_preserved(
    tmp_path: Path, test_case: CaptureOutcomeTestCase
) -> None:
    storage: LocalFilesystemComputeLogStorage = LocalFilesystemComputeLogStorage(
        project_dir=tmp_path
    )
    metadata: CaptureMetadata = build_capture_metadata(
        project_dir=tmp_path, invocation_id="close_failure", started_at=datetime.now(UTC)
    )
    storage.start_capture(metadata)
    capture: ScopedComputeLogCapture = ScopedComputeLogCapture(
        storage=storage,
        metadata=metadata,
        failure_callback=lambda _error, _channel: None,
    )
    real_close: Callable[[], None] = storage.close

    def close_then_fail() -> None:
        real_close()
        raise OSError("controlled close failure")

    with (
        patch.object(TextComputeLogTee, "flush", Mock(side_effect=OSError("flush failure"))),
        patch.object(storage, "close", close_then_fail),
    ):
        result: int = capture.run(operation=Mock(return_value=test_case.expected_exit_code))

    assert result == test_case.expected_exit_code
    assert storage.is_complete(invocation_id=metadata.invocation_id) is False
    with pytest.raises(CaptureStateError, match="closed"):
        storage.append(
            invocation_id=metadata.invocation_id,
            stream=ComputeLogStream.STDOUT,
            data=b"cannot append",
        )


@pytest.mark.parametrize(
    "test_case",
    (
        CaptureOutcomeTestCase(
            description="unexpected exception is re-raised after complete cleanup",
            outcome="exception",
            expected_exit_code=1,
            expected_error_type=ValueError,
        ),
        CaptureOutcomeTestCase(
            description="SystemExit is re-raised with its exit code captured",
            outcome="system_exit",
            expected_exit_code=9,
            expected_error_type=SystemExit,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_operation_exception_when_capturing_then_original_exception_and_terminal_code_remain(
    tmp_path: Path, test_case: CaptureOutcomeTestCase
) -> None:
    storage: LocalFilesystemComputeLogStorage = LocalFilesystemComputeLogStorage(
        project_dir=tmp_path
    )
    metadata: CaptureMetadata = build_capture_metadata(
        project_dir=tmp_path,
        invocation_id=f"outcome_{test_case.expected_exit_code}",
        started_at=datetime.now(UTC),
    )
    storage.start_capture(metadata)
    capture: ScopedComputeLogCapture = ScopedComputeLogCapture(
        storage=storage,
        metadata=metadata,
        failure_callback=lambda _error, _channel: None,
    )
    error_type: type[BaseException] = cast(type[BaseException], test_case.expected_error_type)
    operation: Mock = Mock(side_effect=error_type(test_case.expected_exit_code))

    with pytest.raises(error_type):
        _ = capture.run(operation=operation)
    final_metadata: FinalCaptureMetadata = cast(
        FinalCaptureMetadata,
        storage.get_metadata(invocation_id=metadata.invocation_id),
    )

    assert final_metadata.exit_code == test_case.expected_exit_code
    assert storage.is_complete(invocation_id=metadata.invocation_id) is True
