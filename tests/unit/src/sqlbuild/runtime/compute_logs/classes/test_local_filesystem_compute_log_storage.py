from __future__ import annotations

import io
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sqlbuild.compute_logs import (
    CaptureInventory,
    CaptureMetadata,
    ComputeLogReadChunk,
    ComputeLogStream,
    InvalidCaptureIdError,
    LocalFilesystemComputeLogStorage,
    PruneResult,
)
from sqlbuild.runtime.compute_logs.classes.diagnostic_log_handler import (
    ComputeDiagnosticLogHandler,
)
from sqlbuild.runtime.compute_logs.classes.text_tee import TextComputeLogTee
from tests.unit.src.sqlbuild.runtime.compute_logs.classes._test_types import (
    CursorReadTestCase,
    DiagnosticTestCase,
    InvalidIdentityTestCase,
    RetentionTestCase,
    TeeTestCase,
)
from tests.unit.src.sqlbuild.runtime.compute_logs.classes.helpers import (
    InvalidLogMessage,
    build_capture_metadata,
    build_final_metadata,
)


@pytest.mark.parametrize(
    "test_case",
    (
        CursorReadTestCase(
            description="utf8 code point is split at an exact byte boundary",
            raw="AéB".encode(),
            cursor=0,
            max_bytes=2,
            expected_data=b"A\xc3",
            expected_cursor=2,
        ),
        CursorReadTestCase(
            description="undecodable bytes remain unchanged",
            raw=b"\xff\xfevalue",
            cursor=1,
            max_bytes=3,
            expected_data=b"\xfeva",
            expected_cursor=4,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_raw_stream_when_reading_byte_cursor_then_returns_exact_bounded_bytes(
    tmp_path: Path, test_case: CursorReadTestCase
) -> None:
    storage: LocalFilesystemComputeLogStorage = LocalFilesystemComputeLogStorage(
        project_dir=tmp_path
    )
    started_at: datetime = datetime.now(UTC)
    metadata: CaptureMetadata = build_capture_metadata(
        project_dir=tmp_path, invocation_id="cursor_case", started_at=started_at
    )
    storage.start_capture(metadata)
    storage.append(
        invocation_id=metadata.invocation_id,
        stream=ComputeLogStream.STDOUT,
        data=test_case.raw,
    )

    chunk: ComputeLogReadChunk = storage.read(
        invocation_id=metadata.invocation_id,
        stream=ComputeLogStream.STDOUT,
        cursor=test_case.cursor,
        max_bytes=test_case.max_bytes,
    )

    assert chunk.data == test_case.expected_data
    assert chunk.next_cursor == test_case.expected_cursor
    assert chunk.is_complete is False
    storage.close()


@pytest.mark.parametrize(
    "test_case",
    (
        InvalidIdentityTestCase(
            description="parent traversal",
            invocation_id="../outside",
            expected_error_fragment="ASCII letters",
        ),
        InvalidIdentityTestCase(
            description="path separator",
            invocation_id="safe/name",
            expected_error_fragment="ASCII letters",
        ),
        InvalidIdentityTestCase(
            description="dot segment",
            invocation_id="..",
            expected_error_fragment="ASCII letters",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_unsafe_identity_when_starting_capture_then_rejects_path_input(
    tmp_path: Path, test_case: InvalidIdentityTestCase
) -> None:
    storage: LocalFilesystemComputeLogStorage = LocalFilesystemComputeLogStorage(
        project_dir=tmp_path
    )
    metadata: CaptureMetadata = build_capture_metadata(
        project_dir=tmp_path,
        invocation_id=test_case.invocation_id,
        started_at=datetime.now(UTC),
    )

    with pytest.raises(InvalidCaptureIdError, match=test_case.expected_error_fragment):
        storage.start_capture(metadata)


@pytest.mark.parametrize(
    "test_case",
    (
        RetentionTestCase(
            description="default retention removes only complete captures older than newest twenty",
            complete_count=23,
            expected_deleted_count=3,
            expected_retained_count=20,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_complete_and_incomplete_captures_when_pruning_then_only_oldest_complete_are_removed(
    tmp_path: Path, test_case: RetentionTestCase
) -> None:
    storage: LocalFilesystemComputeLogStorage = LocalFilesystemComputeLogStorage(
        project_dir=tmp_path
    )
    started_at: datetime = datetime.now(UTC)
    for index in range(test_case.complete_count):
        metadata: CaptureMetadata = build_capture_metadata(
            project_dir=tmp_path,
            invocation_id=f"complete_{index:02d}",
            started_at=started_at,
        )
        storage.start_capture(metadata)
        storage.mark_complete(
            build_final_metadata(
                storage=storage,
                initial=metadata,
                completed_at=started_at + timedelta(seconds=index + 1),
            )
        )
    incomplete: CaptureMetadata = build_capture_metadata(
        project_dir=tmp_path, invocation_id="incomplete", started_at=started_at
    )
    storage.start_capture(incomplete)

    result: PruneResult = storage.prune()
    inventory: CaptureInventory = storage.inventory()

    assert len(result.deleted_invocation_ids) == test_case.expected_deleted_count
    assert result.retained_complete_count == test_case.expected_retained_count
    assert inventory.complete_count == test_case.expected_retained_count
    assert inventory.incomplete_count == 1
    assert storage.is_complete(invocation_id=incomplete.invocation_id) is False
    storage.close()


@pytest.mark.parametrize(
    "test_case",
    (
        TeeTestCase(
            description="text and binary buffer writes reach each sink exactly once",
            text="visible ",
            binary=b"\xff\n",
            expected_bytes=b"visible \xff\n",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_text_sink_when_teeing_text_and_binary_then_console_and_capture_match_once(
    tmp_path: Path, test_case: TeeTestCase
) -> None:
    storage: LocalFilesystemComputeLogStorage = LocalFilesystemComputeLogStorage(
        project_dir=tmp_path
    )
    metadata: CaptureMetadata = build_capture_metadata(
        project_dir=tmp_path, invocation_id="tee_case", started_at=datetime.now(UTC)
    )
    storage.start_capture(metadata)
    binary_sink: io.BytesIO = io.BytesIO()
    text_sink: io.TextIOWrapper = io.TextIOWrapper(binary_sink, encoding="utf-8")
    tee: TextComputeLogTee = TextComputeLogTee(
        sink=text_sink,
        storage=storage,
        invocation_id=metadata.invocation_id,
        stream=ComputeLogStream.STDOUT,
    )

    _ = tee.write(test_case.text)
    _ = tee.buffer.write(test_case.binary)
    tee.flush()
    retained: ComputeLogReadChunk = storage.read(
        invocation_id=metadata.invocation_id, stream=ComputeLogStream.STDOUT
    )

    assert binary_sink.getvalue() == test_case.expected_bytes
    assert retained.data == test_case.expected_bytes
    storage.close()


@pytest.mark.parametrize(
    "test_case",
    (
        DiagnosticTestCase(
            description="full SQL is excluded from structured diagnostics",
            sql="SELECT secret_value FROM private_table",
            expected_message=b"SQL diagnostic omitted",
            expected_absent_sql=b"secret_value",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_structured_sql_record_when_capturing_diagnostic_then_full_sql_is_excluded(
    tmp_path: Path, test_case: DiagnosticTestCase
) -> None:
    storage: LocalFilesystemComputeLogStorage = LocalFilesystemComputeLogStorage(
        project_dir=tmp_path
    )
    metadata: CaptureMetadata = build_capture_metadata(
        project_dir=tmp_path, invocation_id="diagnostic_case", started_at=datetime.now(UTC)
    )
    storage.start_capture(metadata)
    handler: ComputeDiagnosticLogHandler = ComputeDiagnosticLogHandler(
        storage=storage, invocation_id=metadata.invocation_id
    )
    invalid_record: logging.LogRecord = logging.LogRecord(
        name="sqlbuild.adapter",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg=InvalidLogMessage(),
        args=(),
        exc_info=None,
    )
    invalid_record.sqlbuild_invocation_id = metadata.invocation_id
    record: logging.LogRecord = logging.LogRecord(
        name="sqlbuild.adapter",
        level=logging.DEBUG,
        pathname=__file__,
        lineno=1,
        msg="SELECT %s FROM private_table",
        args=("secret_parameter",),
        exc_info=None,
    )
    record.sqlbuild_invocation_id = metadata.invocation_id
    record.sqlbuild_run_id = "private_table_run"
    record.sqlbuild_error_type = "secret_parameter_error"
    record.sqlbuild_sql = test_case.sql

    handler.emit(invalid_record)
    handler.emit(record)
    retained: ComputeLogReadChunk = storage.read(
        invocation_id=metadata.invocation_id,
        stream=ComputeLogStream.DIAGNOSTICS,
    )

    assert test_case.expected_message in retained.data
    assert test_case.expected_absent_sql not in retained.data
    assert b"secret_parameter" not in retained.data
    assert b"private_table" not in retained.data
    assert retained.data.endswith(b"\n")
    storage.close()
