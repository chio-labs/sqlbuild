import json
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
from sqlbuild.diagnostics.constants import SQL_DIGEST_FIELD
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event
from sqlbuild.diagnostics.main.log_sql import log_sql
from sqlbuild.diagnostics.models import DiagnosticRoutingOptions
from sqlbuild.observability import ExecutionIdentity, identity_scope
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
    DiagnosticRoutingTestCase,
)
from tests.unit.src.sqlbuild.runtime.compute_logs.classes.helpers import (
    AccessFailureTextSink,
    HostRecordingLogHandler,
    build_capture_metadata,
)

_PRIVATE_SQL: str = "SELECT * FROM private_table WHERE password = 'very-secret'"


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
    assert storage.is_complete(invocation_id=metadata.invocation_id) is True


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
    assert storage.is_complete(invocation_id=metadata.invocation_id) is True


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


@pytest.mark.parametrize(
    "test_case",
    (
        DiagnosticRoutingTestCase(
            description="default SQL policy redacts every destination",
            debug=False,
            include_sql_text=False,
            expected_sql_in_diagnostics=False,
            expected_internal_console_count=0,
            expected_plain_console_count=0,
            expected_structured_console_count=0,
            expected_sql_run_id=None,
            expected_sql_statement_id=None,
        ),
        DiagnosticRoutingTestCase(
            description="debug console adds internal families without SQL text",
            debug=True,
            include_sql_text=False,
            expected_sql_in_diagnostics=False,
            expected_internal_console_count=1,
            expected_plain_console_count=1,
            expected_structured_console_count=1,
            expected_sql_run_id=None,
            expected_sql_statement_id=None,
        ),
        DiagnosticRoutingTestCase(
            description="SQL opt in without debug remains diagnostics only",
            debug=False,
            include_sql_text=True,
            expected_sql_in_diagnostics=True,
            expected_internal_console_count=0,
            expected_plain_console_count=0,
            expected_structured_console_count=0,
            expected_sql_run_id="matrix-run",
            expected_sql_statement_id="matrix-statement",
        ),
        DiagnosticRoutingTestCase(
            description="explicit SQL policy confines text to diagnostic files",
            debug=True,
            include_sql_text=True,
            expected_sql_in_diagnostics=True,
            expected_internal_console_count=1,
            expected_plain_console_count=1,
            expected_structured_console_count=1,
            expected_sql_run_id="matrix-run",
            expected_sql_statement_id="matrix-statement",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_internal_user_and_sql_records_when_routing_then_policy_is_destination_specific(
    tmp_path: Path,
    test_case: DiagnosticRoutingTestCase,
    capsys: pytest.CaptureFixture[str],
) -> None:
    storage: LocalFilesystemComputeLogStorage = LocalFilesystemComputeLogStorage(
        project_dir=tmp_path
    )
    metadata: CaptureMetadata = build_capture_metadata(
        project_dir=tmp_path,
        invocation_id=f"route_{test_case.debug}",
        started_at=datetime.now(UTC),
    )
    storage.start_capture(metadata)
    capture: ScopedComputeLogCapture = ScopedComputeLogCapture(
        storage=storage,
        metadata=metadata,
        failure_callback=lambda _error, _channel: None,
        routing_options=DiagnosticRoutingOptions(
            debug_console=test_case.debug,
            include_sql_text=test_case.include_sql_text,
        ),
    )
    root_logger: logging.Logger = logging.getLogger()
    hostile_host: HostRecordingLogHandler = HostRecordingLogHandler()
    prior_root_level: int = root_logger.level
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(hostile_host)

    def emit_records() -> int:
        logging.getLogger("sqlbuild.route").debug(
            "plain internal api_key='internal key with spaces'"
        )
        log_debug_event(
            logger=logging.getLogger("sqlbuild.route"),
            message='structured internal client_secret="client secret with spaces"',
            sqlbuild_channel="matrix",
        )
        with identity_scope(
            ExecutionIdentity(
                invocation_id="ambient-invocation",
                run_id="matrix-run",
                statement_id="matrix-statement",
            )
        ):
            log_sql(logger=logging.getLogger("sqlbuild.route"), sql=_PRIVATE_SQL, action="submit")
        user_logger: logging.Logger = logging.getLogger("project.pipeline")
        prior_user_level: int = user_logger.level
        user_logger.setLevel(logging.NOTSET)
        user_logger.debug("user debug access_key=debug-access-key")
        user_logger.info(
            "connected dsn=postgres://user:password@host Authorization: Bearer bearer-value "
            "authorization=Basic basic-value API-Key=hyphen-api-key "
            "access_key=visible-access-key private_key='private key with spaces' "
            "password='quoted password with spaces' secret=\"quoted secret with spaces\"",
            extra={
                "password": "structured-password",
                "payload": {
                    "api_key": "nested-api-key",
                    "items": [{"refresh_token": "nested-refresh-token"}],
                },
            },
        )
        user_logger.setLevel(prior_user_level)
        return 0

    try:
        result: int = capture.run(operation=emit_records)
        restored_root_level: int = root_logger.level
    finally:
        root_logger.removeHandler(hostile_host)
        root_logger.setLevel(prior_root_level)
    console: str = capsys.readouterr().err
    capture_dir: Path = tuple((tmp_path / "logs").glob("*/*"))[0]
    diagnostic_lines: list[dict[str, object]] = [
        json.loads(line)
        for line in (capture_dir / "diagnostics.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    diagnostic_text: str = json.dumps(diagnostic_lines)

    assert result == 0
    assert restored_root_level == logging.DEBUG
    assert diagnostic_text.count(_PRIVATE_SQL) == int(test_case.expected_sql_in_diagnostics)
    assert not (tmp_path / "target" / "sqlbuild.log").exists()
    assert _PRIVATE_SQL not in console
    assert _PRIVATE_SQL not in repr([record.__dict__ for record in hostile_host.records])
    assert hostile_host.was_closed is False
    host_messages: list[str] = [record.getMessage() for record in hostile_host.records]
    assert host_messages.count("submit SQL") == 1
    host_sql_record: logging.LogRecord = hostile_host.records[host_messages.index("submit SQL")]
    assert SQL_DIGEST_FIELD in host_sql_record.__dict__
    assert (
        sum(
            record.getMessage() == "user debug access_key=debug-access-key"
            for record in hostile_host.records
        )
        == 1
    )
    assert console.count("SQL diagnostic omitted") == test_case.expected_internal_console_count
    assert console.count("plain internal api_key=[REDACTED]") == (
        test_case.expected_plain_console_count
    )
    assert console.count("structured internal client_secret=[REDACTED]") == (
        test_case.expected_structured_console_count
    )
    assert (
        console.count(
            "connected dsn=[REDACTED] Authorization: [REDACTED] "
            "authorization=[REDACTED] API-Key=[REDACTED]"
        )
        == 1
    )
    for secret in (
        "internal key with spaces",
        "client secret with spaces",
        "debug-access-key",
        "visible-access-key",
        "private key with spaces",
        "quoted password with spaces",
        "quoted secret with spaces",
        "bearer-value",
        "basic-value",
        "hyphen-api-key",
        "structured-password",
        "nested-api-key",
        "nested-refresh-token",
    ):
        assert secret not in diagnostic_text
        assert secret not in console
    assert "sql_digest" in diagnostic_text
    diagnostic_loggers: list[object] = [line["logger"] for line in diagnostic_lines]
    assert diagnostic_loggers.count("sqlbuild.sql") == 1
    sql_diagnostic: dict[str, object] = diagnostic_lines[diagnostic_loggers.index("sqlbuild.sql")]
    assert sql_diagnostic["invocation_id"] == metadata.invocation_id
    assert sql_diagnostic["run_id"] == test_case.expected_sql_run_id
    assert sql_diagnostic["statement_id"] == test_case.expected_sql_statement_id
    assert diagnostic_text.count("plain internal api_key=[REDACTED]") == 1
    assert diagnostic_text.count("structured internal client_secret=[REDACTED]") == 1
    assert diagnostic_text.count("user debug") == 0
