import json
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO, cast
from unittest.mock import Mock, patch

import pytest

from sqlbuild.compute_logs import (
    CaptureInventory,
    CaptureMetadata,
    CaptureStateError,
    ComputeLogMetadataError,
    ComputeLogPathError,
    ComputeLogReadChunk,
    ComputeLogStream,
    FinalCaptureMetadata,
    LocalFilesystemComputeLogStorage,
)
from sqlbuild.observability import DiagnosticLog
from tests.unit.src.sqlbuild.runtime.compute_logs.classes._test_types import (
    PathSafetyTestCase,
    RecoveryTestCase,
    RetentionTestCase,
)
from tests.unit.src.sqlbuild.runtime.compute_logs.classes.helpers import (
    FailOnceBinaryWriter,
    build_capture_metadata,
    build_final_metadata,
)


@pytest.mark.parametrize(
    "test_case",
    (
        RecoveryTestCase(
            description="count mismatch remains active and can be retried",
            initial_bytes=b"first",
            retry_bytes=b" second",
            expected_bytes=b"first second",
            expected_complete=True,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_mismatched_completion_counts_when_retrying_then_capture_remains_recoverable(
    tmp_path: Path, test_case: RecoveryTestCase
) -> None:
    storage: LocalFilesystemComputeLogStorage = LocalFilesystemComputeLogStorage(
        project_dir=tmp_path
    )
    initial: CaptureMetadata = build_capture_metadata(
        project_dir=tmp_path, invocation_id="completion_retry", started_at=datetime.now(UTC)
    )
    storage.start_capture(initial)
    storage.append(
        invocation_id=initial.invocation_id,
        stream=ComputeLogStream.STDOUT,
        data=test_case.initial_bytes,
    )
    valid_before_retry: FinalCaptureMetadata = build_final_metadata(
        storage=storage, initial=initial, completed_at=datetime.now(UTC)
    )
    mismatched: FinalCaptureMetadata = replace(
        valid_before_retry, stdout_bytes=valid_before_retry.stdout_bytes + 1
    )

    with pytest.raises(ComputeLogMetadataError, match="byte counts"):
        storage.mark_complete(mismatched)
    storage.append(
        invocation_id=initial.invocation_id,
        stream=ComputeLogStream.STDOUT,
        data=test_case.retry_bytes,
    )
    storage.mark_complete(
        build_final_metadata(storage=storage, initial=initial, completed_at=datetime.now(UTC))
    )
    retained: ComputeLogReadChunk = storage.read(
        invocation_id=initial.invocation_id, stream=ComputeLogStream.STDOUT
    )

    assert retained.data == test_case.expected_bytes
    assert retained.is_complete is test_case.expected_complete
    storage.close()


@pytest.mark.parametrize(
    "test_case",
    (
        RecoveryTestCase(
            description="writer close failure deactivates capture and closes retryable handle",
            initial_bytes=b"captured",
            retry_bytes=b"",
            expected_bytes=b"captured",
            expected_complete=False,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_writer_close_failure_when_completing_then_incomplete_state_remains_coherent(
    tmp_path: Path, test_case: RecoveryTestCase
) -> None:
    storage: LocalFilesystemComputeLogStorage = LocalFilesystemComputeLogStorage(
        project_dir=tmp_path
    )
    initial: CaptureMetadata = build_capture_metadata(
        project_dir=tmp_path, invocation_id="writer_close_failure", started_at=datetime.now(UTC)
    )
    storage.start_capture(initial)
    storage.append(
        invocation_id=initial.invocation_id,
        stream=ComputeLogStream.STDOUT,
        data=test_case.initial_bytes,
    )
    original_writer: BinaryIO = storage._writers[initial.invocation_id][ComputeLogStream.STDOUT]
    failing_writer: FailOnceBinaryWriter = FailOnceBinaryWriter(original_writer)
    storage._writers[initial.invocation_id][ComputeLogStream.STDOUT] = cast(
        BinaryIO, failing_writer
    )
    final_metadata: FinalCaptureMetadata = build_final_metadata(
        storage=storage, initial=initial, completed_at=datetime.now(UTC)
    )

    with pytest.raises(CaptureStateError, match="stream close failed"):
        storage.mark_complete(final_metadata)
    retained: ComputeLogReadChunk = storage.read(
        invocation_id=initial.invocation_id, stream=ComputeLogStream.STDOUT
    )

    assert retained.data == test_case.expected_bytes
    assert retained.is_complete is test_case.expected_complete
    assert failing_writer.closed is True
    assert failing_writer.close_calls == 2
    storage.close()


@pytest.mark.parametrize(
    "test_case",
    (
        RecoveryTestCase(
            description="failed staged publication leaves no visible capture",
            initial_bytes=b"",
            retry_bytes=b"",
            expected_bytes=b"",
            expected_complete=False,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_initial_metadata_failure_when_publishing_then_staging_directory_is_cleaned(
    tmp_path: Path, test_case: RecoveryTestCase
) -> None:
    storage: LocalFilesystemComputeLogStorage = LocalFilesystemComputeLogStorage(
        project_dir=tmp_path
    )
    initial: CaptureMetadata = build_capture_metadata(
        project_dir=tmp_path, invocation_id="staged_failure", started_at=datetime.now(UTC)
    )

    with (
        patch.object(
            LocalFilesystemComputeLogStorage,
            "_write_metadata",
            Mock(side_effect=OSError("controlled metadata failure")),
        ),
        pytest.raises(OSError, match="controlled metadata failure"),
    ):
        storage.start_capture(initial)
    date_dir: Path = storage.root / initial.capture_date
    entries: tuple[Path, ...] = tuple(date_dir.iterdir())
    inventory: CaptureInventory = storage.inventory()

    assert entries == ()
    assert inventory.captures == ()
    assert test_case.expected_bytes == b""
    assert test_case.expected_complete is False
    storage.close()


@pytest.mark.parametrize(
    "test_case",
    (
        RecoveryTestCase(
            description="concurrent hidden staging directory is ignored by inventory",
            initial_bytes=b"",
            retry_bytes=b"",
            expected_bytes=b"",
            expected_complete=False,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_hidden_publication_window_when_inventorying_then_staging_is_ignored(
    tmp_path: Path, test_case: RecoveryTestCase
) -> None:
    storage: LocalFilesystemComputeLogStorage = LocalFilesystemComputeLogStorage(
        project_dir=tmp_path
    )
    date_dir: Path = storage.root / datetime.now(UTC).date().isoformat()
    date_dir.mkdir()
    staging_dir: Path = date_dir / ".capture.controlled.tmp"
    staging_dir.mkdir()

    inventory: CaptureInventory = storage.inventory()

    assert inventory.captures == ()
    assert test_case.expected_bytes == b""
    assert test_case.expected_complete is False
    storage.close()


@pytest.mark.parametrize(
    "test_case",
    (
        PathSafetyTestCase(
            description="configured root symlink is rejected",
            alias_kind="root",
            expected_error_fragment="root cannot be a symlink",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_symlink_root_when_opening_storage_then_configured_alias_is_rejected(
    tmp_path: Path, test_case: PathSafetyTestCase
) -> None:
    actual_root: Path = tmp_path / "actual"
    actual_root.mkdir()
    alias_root: Path = tmp_path / "alias"
    alias_root.symlink_to(actual_root, target_is_directory=True)

    with pytest.raises(ComputeLogPathError, match=test_case.expected_error_fragment):
        _ = LocalFilesystemComputeLogStorage(project_dir=tmp_path, root=alias_root)
    assert test_case.alias_kind == "root"


@pytest.mark.parametrize(
    "test_case",
    (
        PathSafetyTestCase(
            description="date directory symlink is rejected",
            alias_kind="date",
            expected_error_fragment="cannot be a symlink",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_symlink_date_when_inventorying_then_alias_is_rejected(
    tmp_path: Path, test_case: PathSafetyTestCase
) -> None:
    actual_root: Path = tmp_path / "actual"
    actual_root.mkdir()
    storage: LocalFilesystemComputeLogStorage = LocalFilesystemComputeLogStorage(
        project_dir=tmp_path
    )
    started_at: datetime = datetime.now(UTC)
    date_dir: Path = storage.root / started_at.date().isoformat()
    date_dir.symlink_to(actual_root, target_is_directory=True)

    with pytest.raises(ComputeLogPathError, match=test_case.expected_error_fragment):
        _ = storage.inventory()
    assert test_case.alias_kind == "date"


@pytest.mark.parametrize(
    "test_case",
    (
        PathSafetyTestCase(
            description="capture directory symlink is rejected",
            alias_kind="capture",
            expected_error_fragment="cannot be a symlink",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_symlink_capture_when_reopening_then_alias_is_rejected(
    tmp_path: Path, test_case: PathSafetyTestCase
) -> None:
    storage: LocalFilesystemComputeLogStorage = LocalFilesystemComputeLogStorage(
        project_dir=tmp_path
    )
    started_at: datetime = datetime.now(UTC)
    date_dir: Path = storage.root / started_at.date().isoformat()
    initial: CaptureMetadata = build_capture_metadata(
        project_dir=tmp_path, invocation_id="real_capture", started_at=started_at
    )
    storage.start_capture(initial)
    storage.close()
    alias_capture: Path = date_dir / "alias_capture"
    alias_capture.symlink_to(date_dir / initial.invocation_id, target_is_directory=True)
    with pytest.raises(ComputeLogPathError, match=test_case.expected_error_fragment):
        _ = storage.get_metadata(invocation_id="alias_capture")
    assert test_case.alias_kind == "capture"


@pytest.mark.parametrize(
    "test_case",
    (
        PathSafetyTestCase(
            description="metadata identity mismatch is rejected",
            alias_kind="metadata",
            expected_error_fragment="does not match capture directory",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_mismatched_metadata_when_reopening_then_directory_identity_is_authoritative(
    tmp_path: Path, test_case: PathSafetyTestCase
) -> None:
    storage: LocalFilesystemComputeLogStorage = LocalFilesystemComputeLogStorage(
        project_dir=tmp_path
    )
    initial: CaptureMetadata = build_capture_metadata(
        project_dir=tmp_path, invocation_id="metadata_owner", started_at=datetime.now(UTC)
    )
    storage.start_capture(initial)
    storage.close()
    metadata_path: Path = (
        storage.root / initial.capture_date / initial.invocation_id / "metadata.json"
    )
    payload: dict[str, object] = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["invocation_id"] = "different_owner"
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ComputeLogMetadataError, match=test_case.expected_error_fragment):
        _ = storage.get_metadata(invocation_id=initial.invocation_id)


@pytest.mark.parametrize(
    "test_case",
    (
        PathSafetyTestCase(
            description="metadata date mismatch is rejected",
            alias_kind="metadata_date",
            expected_error_fragment="does not match date directory",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_mismatched_metadata_date_when_reopening_then_date_directory_is_authoritative(
    tmp_path: Path, test_case: PathSafetyTestCase
) -> None:
    storage: LocalFilesystemComputeLogStorage = LocalFilesystemComputeLogStorage(
        project_dir=tmp_path
    )
    initial: CaptureMetadata = build_capture_metadata(
        project_dir=tmp_path, invocation_id="date_owner", started_at=datetime.now(UTC)
    )
    storage.start_capture(initial)
    storage.close()
    metadata_path: Path = (
        storage.root / initial.capture_date / initial.invocation_id / "metadata.json"
    )
    payload: dict[str, object] = json.loads(metadata_path.read_text(encoding="utf-8"))
    moved_start: datetime = initial.started_at + timedelta(days=1)
    payload["started_at"] = moved_start.isoformat().replace("+00:00", "Z")
    payload["capture_date"] = moved_start.date().isoformat()
    metadata_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ComputeLogMetadataError, match=test_case.expected_error_fragment):
        _ = storage.get_metadata(invocation_id=initial.invocation_id)
    assert test_case.alias_kind == "metadata_date"


@pytest.mark.parametrize(
    "test_case",
    (
        RetentionTestCase(
            description="concurrent diagnostic appends remain complete JSON lines",
            complete_count=32,
            expected_deleted_count=0,
            expected_retained_count=32,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_concurrent_diagnostics_when_appending_then_serialized_jsonl_remains_valid(
    tmp_path: Path, test_case: RetentionTestCase
) -> None:
    storage: LocalFilesystemComputeLogStorage = LocalFilesystemComputeLogStorage(
        project_dir=tmp_path
    )
    initial: CaptureMetadata = build_capture_metadata(
        project_dir=tmp_path,
        invocation_id="concurrent_diagnostics",
        started_at=datetime.now(UTC),
    )
    storage.start_capture(initial)
    records: tuple[DiagnosticLog, ...] = tuple(
        DiagnosticLog(
            schema_version=1,
            producer="sqlbuild",
            producer_version="test",
            occurred_at=datetime.now(UTC),
            severity="info",
            logger="sqlbuild.test",
            source="test",
            message=f"record {index}",
            invocation_id=initial.invocation_id,
        )
        for index in range(test_case.complete_count)
    )
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures: tuple[Future[None], ...] = tuple(
            executor.submit(
                storage.append_diagnostic,
                invocation_id=initial.invocation_id,
                record=record,
            )
            for record in records
        )
        for future in futures:
            future.result()
    retained: ComputeLogReadChunk = storage.read(
        invocation_id=initial.invocation_id,
        stream=ComputeLogStream.DIAGNOSTICS,
    )
    decoded: tuple[dict[str, object], ...] = tuple(
        json.loads(line) for line in retained.data.decode().splitlines()
    )

    assert len(decoded) == test_case.expected_retained_count
    assert test_case.expected_deleted_count == 0
    storage.close()
