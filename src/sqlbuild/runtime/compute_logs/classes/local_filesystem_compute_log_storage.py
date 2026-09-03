"""Project-local filesystem compute log storage."""

from __future__ import annotations

import os
import re
import shutil
import threading
from datetime import UTC
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Literal, Self, overload
from uuid import uuid4

from filelock import FileLock

from sqlbuild.observability import DiagnosticLog, diagnostic_log_to_json
from sqlbuild.runtime.compute_logs._helpers.metadata import metadata_from_json, metadata_to_json
from sqlbuild.runtime.compute_logs.constants import (
    COMPLETE_FILE_NAME,
    COMPUTE_LOG_FORMAT_VERSION,
    DEFAULT_RETENTION_COUNT,
    MAX_READ_BYTES,
    METADATA_FILE_NAME,
    PRUNE_LOCK_FILE_NAME,
)
from sqlbuild.runtime.compute_logs.exceptions import (
    CaptureAlreadyExistsError,
    CaptureNotFoundError,
    CaptureStateError,
    ComputeLogMetadataError,
    ComputeLogPathError,
    InvalidCaptureIdError,
    InvalidComputeLogCursorError,
    InvalidComputeLogLimitError,
)
from sqlbuild.runtime.compute_logs.models import (
    CaptureByteCounts,
    CaptureInventory,
    CaptureInventoryItem,
    CaptureMetadata,
    ComputeLogReadChunk,
    FinalCaptureMetadata,
    PruneResult,
)
from sqlbuild.runtime.compute_logs.types import ByteCursor, ComputeLogStream

_CAPTURE_ID_PATTERN: re.Pattern[str] = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_DATE_PATTERN: re.Pattern[str] = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_STREAM_FILES: dict[ComputeLogStream, str] = {
    ComputeLogStream.STDOUT: "stdout.log",
    ComputeLogStream.STDERR: "stderr.log",
    ComputeLogStream.DIAGNOSTICS: "diagnostics.jsonl",
}


class LocalFilesystemComputeLogStorage:
    """Ordered fsync capture storage subject to underlying filesystem and hardware guarantees."""

    def __init__(
        self,
        *,
        project_dir: Path,
        root: Path | None = None,
        retention_count: int | None = DEFAULT_RETENTION_COUNT,
    ) -> None:
        if retention_count is not None and retention_count < 0:
            raise InvalidComputeLogLimitError("retention_count must be nonnegative or None")
        configured_root: Path = project_dir / "logs" if root is None else root
        if configured_root.is_symlink():
            raise ComputeLogPathError("configured compute log root cannot be a symlink")
        configured_root.mkdir(parents=True, exist_ok=True)
        if configured_root.is_symlink():
            raise ComputeLogPathError("configured compute log root cannot be a symlink")
        self._root: Path = configured_root.resolve(strict=True)
        if not self._root.is_dir():
            raise ComputeLogPathError("compute log root must be a directory")
        self._retention_count: int | None = retention_count
        self._writers: dict[str, dict[ComputeLogStream, BinaryIO]] = {}
        self._locks: dict[str, threading.RLock] = {}
        self._state_lock: threading.RLock = threading.RLock()
        self._closed: bool = False

    @property
    def root(self) -> Path:
        """Return the resolved configured log root."""

        return self._root

    def start_capture(self, metadata: CaptureMetadata) -> None:
        """Create one incomplete capture and open its serialized append streams."""

        self._ensure_open()
        self._validate_metadata(metadata=metadata)
        date_dir: Path = self._root / metadata.capture_date
        self._ensure_not_symlink(path=date_dir)
        date_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_not_symlink(path=date_dir)
        self._ensure_contained(path=date_dir)
        capture_dir: Path = date_dir / metadata.invocation_id
        self._ensure_contained(path=capture_dir)
        with self._state_lock:
            existing: Path | None = self._find_capture(
                invocation_id=metadata.invocation_id, missing_ok=True
            )
            if existing is not None:
                raise CaptureAlreadyExistsError(
                    f"capture already exists for invocation {metadata.invocation_id!r}"
                )
            staging_dir: Path = date_dir / f".{metadata.invocation_id}.{uuid4().hex}.tmp"
            self._ensure_contained(path=staging_dir)
            staging_dir.mkdir(parents=False, exist_ok=False)
            writers: dict[ComputeLogStream, BinaryIO] = {}
            published: bool = False
            try:
                for stream, file_name in _STREAM_FILES.items():
                    writers[stream] = (staging_dir / file_name).open("xb")
                self._write_metadata(capture_dir=staging_dir, metadata=metadata)
                for writer in writers.values():
                    writer.flush()
                    os.fsync(writer.fileno())
                self._fsync_directory(staging_dir)
                staging_dir.rename(capture_dir)
                published = True
                self._fsync_directory(date_dir)
            except BaseException:
                for writer in writers.values():
                    try:
                        if not writer.closed:
                            writer.close()
                    except Exception as cleanup_error:
                        _ = cleanup_error
                failed_dir: Path = capture_dir if published else staging_dir
                shutil.rmtree(failed_dir, ignore_errors=True)
                raise
            self._writers[metadata.invocation_id] = writers
            self._locks[metadata.invocation_id] = threading.RLock()

    def append(self, *, invocation_id: str, stream: ComputeLogStream, data: bytes) -> None:
        """Append exact raw bytes and make them visible to concurrent readers."""

        self._ensure_open()
        self._validate_capture_id(invocation_id)
        if not isinstance(stream, ComputeLogStream):
            raise CaptureStateError("stream must be a ComputeLogStream")
        if not isinstance(data, bytes):
            raise CaptureStateError("compute log append data must be bytes")
        lock: threading.RLock = self._capture_lock(invocation_id)
        with lock:
            writer: BinaryIO = self._active_writers(invocation_id)[stream]
            writer.write(data)
            writer.flush()

    def append_diagnostic(self, *, invocation_id: str, record: DiagnosticLog) -> None:
        """Append one validated deterministic UTF-8 diagnostic JSON line."""

        if not isinstance(record, DiagnosticLog):
            raise CaptureStateError("diagnostic append requires DiagnosticLog")
        encoded: bytes = (diagnostic_log_to_json(record) + "\n").encode("utf-8")
        self.append(
            invocation_id=invocation_id,
            stream=ComputeLogStream.DIAGNOSTICS,
            data=encoded,
        )

    def read(
        self,
        *,
        invocation_id: str,
        stream: ComputeLogStream,
        cursor: ByteCursor = 0,
        max_bytes: int = MAX_READ_BYTES,
    ) -> ComputeLogReadChunk:
        """Read at most the public byte limit from an exact stream offset."""

        self._validate_capture_id(invocation_id)
        if not isinstance(stream, ComputeLogStream):
            raise CaptureStateError("stream must be a ComputeLogStream")
        if type(cursor) is not int or cursor < 0:
            raise InvalidComputeLogCursorError("cursor must be a nonnegative integer")
        if type(max_bytes) is not int or max_bytes < 1 or max_bytes > MAX_READ_BYTES:
            raise InvalidComputeLogLimitError(
                f"max_bytes must be a positive integer no greater than {MAX_READ_BYTES}"
            )
        capture_dir: Path = self._find_capture(invocation_id=invocation_id)
        path: Path = capture_dir / _STREAM_FILES[stream]
        marker: Path = capture_dir / COMPLETE_FILE_NAME
        self._ensure_contained(path=path)
        self._ensure_contained(path=marker)
        complete: bool = marker.is_file()
        if not path.exists():
            return ComputeLogReadChunk(data=b"", next_cursor=cursor, is_complete=complete)
        size: int = path.stat().st_size
        if cursor > size:
            raise InvalidComputeLogCursorError(
                f"cursor {cursor} is beyond current stream size {size}"
            )
        with path.open("rb") as stream_file:
            stream_file.seek(cursor)
            data: bytes = stream_file.read(max_bytes)
            next_cursor: int = stream_file.tell()
        return ComputeLogReadChunk(data=data, next_cursor=next_cursor, is_complete=complete)

    def get_metadata(self, *, invocation_id: str) -> CaptureMetadata | FinalCaptureMetadata:
        """Read the currently atomically published metadata document."""

        capture_dir: Path = self._find_capture(invocation_id=invocation_id)
        path: Path = capture_dir / METADATA_FILE_NAME
        self._ensure_contained(path=path)
        try:
            metadata: CaptureMetadata | FinalCaptureMetadata = metadata_from_json(
                path.read_text(encoding="utf-8")
            )
            self._validate_metadata(metadata=metadata)
            self._validate_directory_metadata(capture_dir=capture_dir, metadata=metadata)
            return metadata
        except OSError as error:
            raise ComputeLogMetadataError(f"unable to read capture metadata: {error}") from error

    def get_byte_count(self, *, invocation_id: str, stream: ComputeLogStream) -> int:
        """Return the current raw byte count for one stream."""

        if not isinstance(stream, ComputeLogStream):
            raise CaptureStateError("stream must be a ComputeLogStream")
        counts: CaptureByteCounts = self.get_byte_counts(invocation_id=invocation_id)
        if stream == ComputeLogStream.STDOUT:
            return counts.stdout_bytes
        if stream == ComputeLogStream.STDERR:
            return counts.stderr_bytes
        return counts.diagnostics_bytes

    def get_byte_counts(self, *, invocation_id: str) -> CaptureByteCounts:
        """Return one lock-consistent snapshot of all stream sizes."""

        self._validate_capture_id(invocation_id)
        with self._state_lock:
            lock: threading.RLock | None = self._locks.get(invocation_id)
        if lock is None:
            return self._read_byte_counts(invocation_id=invocation_id)
        with lock:
            return self._read_byte_counts(invocation_id=invocation_id)

    def is_complete(self, *, invocation_id: str) -> bool:
        """Return capture-close evidence without asserting execution lifecycle status."""

        capture_dir: Path = self._find_capture(invocation_id=invocation_id)
        marker: Path = capture_dir / COMPLETE_FILE_NAME
        self._ensure_contained(path=marker)
        return marker.is_file()

    def mark_complete(self, metadata: FinalCaptureMetadata) -> None:
        """Flush, fsync, and close streams before publishing final metadata and marker."""

        self._ensure_open()
        self._validate_metadata(metadata=metadata)
        lock: threading.RLock = self._capture_lock(metadata.invocation_id)
        with lock:
            capture_dir: Path = self._find_capture(invocation_id=metadata.invocation_id)
            initial_metadata: CaptureMetadata | FinalCaptureMetadata = self.get_metadata(
                invocation_id=metadata.invocation_id
            )
            if not isinstance(initial_metadata, CaptureMetadata) or (
                initial_metadata.started_at != metadata.started_at
                or initial_metadata.capture_date != metadata.capture_date
                or initial_metadata.command != metadata.command
                or initial_metadata.project_dir != metadata.project_dir
                or initial_metadata.target != metadata.target
                or initial_metadata.run_id != metadata.run_id
            ):
                raise ComputeLogMetadataError(
                    "final metadata does not match capture start metadata"
                )
            writers: dict[ComputeLogStream, BinaryIO] = self._active_writers(metadata.invocation_id)
            actual_counts: dict[ComputeLogStream, int] = {}
            for stream, writer in writers.items():
                writer.flush()
                actual_counts[stream] = writer.tell()
            if (
                metadata.stdout_bytes != actual_counts[ComputeLogStream.STDOUT]
                or metadata.stderr_bytes != actual_counts[ComputeLogStream.STDERR]
                or metadata.diagnostics_bytes != actual_counts[ComputeLogStream.DIAGNOSTICS]
            ):
                raise ComputeLogMetadataError("final byte counts do not match captured streams")
            for writer in writers.values():
                os.fsync(writer.fileno())
            close_error: Exception | None = None
            for writer in writers.values():
                try:
                    writer.close()
                except Exception as error:
                    if close_error is None:
                        close_error = error
                    try:
                        if not writer.closed:
                            writer.close()
                    except Exception as retry_error:
                        if close_error is None:
                            close_error = retry_error
            with self._state_lock:
                self._writers.pop(metadata.invocation_id, None)
                self._locks.pop(metadata.invocation_id, None)
            if close_error is not None:
                raise CaptureStateError("capture stream close failed") from close_error
            self._write_metadata(capture_dir=capture_dir, metadata=metadata)
            marker: Path = capture_dir / COMPLETE_FILE_NAME
            with marker.open("xb") as marker_file:
                marker_file.flush()
                os.fsync(marker_file.fileno())
            self._fsync_directory(capture_dir)

    def delete(self, *, invocation_id: str) -> None:
        """Delete a complete inactive capture without following symlinks."""

        self._validate_capture_id(invocation_id)
        with self._state_lock:
            if invocation_id in self._writers:
                raise CaptureStateError("active captures cannot be deleted")
            capture_dir: Path = self._find_capture(invocation_id=invocation_id)
            marker: Path = capture_dir / COMPLETE_FILE_NAME
            self._ensure_contained(path=marker)
            if not marker.is_file():
                raise CaptureStateError("incomplete captures cannot be deleted")
            self._ensure_contained(path=capture_dir)
            shutil.rmtree(capture_dir)

    def prune(self, retain_count: int | None = None) -> PruneResult:
        """Retain the newest complete captures while never deleting incomplete captures."""

        effective_count: int | None = (
            self._retention_count if retain_count is None else retain_count
        )
        if effective_count is None:
            inventory: CaptureInventory = self.inventory()
            return PruneResult((), inventory.complete_count, inventory.incomplete_count)
        if type(effective_count) is not int or effective_count < 0:
            raise InvalidComputeLogLimitError("retain_count must be nonnegative or None")
        lock_path: Path = self._root / PRUNE_LOCK_FILE_NAME
        self._ensure_contained(path=lock_path)
        with FileLock(lock_path):
            inventory = self.inventory()
            complete: list[CaptureInventoryItem] = [
                item for item in inventory.captures if item.is_complete
            ]
            complete.sort(key=self._completion_key, reverse=True)
            deleted: list[str] = []
            for item in complete[effective_count:]:
                capture_dir: Path = Path(item.path)
                self._ensure_not_symlink(path=capture_dir)
                self._ensure_contained(path=capture_dir)
                marker: Path = capture_dir / COMPLETE_FILE_NAME
                self._ensure_contained(path=marker)
                if not marker.is_file():
                    continue
                self.delete(invocation_id=item.invocation_id)
                deleted.append(item.invocation_id)
            return PruneResult(
                deleted_invocation_ids=tuple(deleted),
                retained_complete_count=len(complete) - len(deleted),
                retained_incomplete_count=inventory.incomplete_count,
            )

    def inventory(self) -> CaptureInventory:
        """Inventory complete and abandoned captures without synthesizing lifecycle state."""

        captures: list[CaptureInventoryItem] = []
        for date_dir in sorted(self._root.iterdir()):
            if date_dir.name == PRUNE_LOCK_FILE_NAME:
                continue
            if not _DATE_PATTERN.fullmatch(date_dir.name):
                continue
            self._ensure_not_symlink(path=date_dir)
            self._ensure_contained(path=date_dir)
            if not date_dir.is_dir():
                continue
            for capture_dir in sorted(date_dir.iterdir()):
                if capture_dir.name.startswith("."):
                    continue
                self._ensure_not_symlink(path=capture_dir)
                self._ensure_contained(path=capture_dir)
                if not capture_dir.is_dir():
                    continue
                metadata_path: Path = capture_dir / METADATA_FILE_NAME
                marker_path: Path = capture_dir / COMPLETE_FILE_NAME
                self._ensure_contained(path=metadata_path)
                self._ensure_contained(path=marker_path)
                metadata: CaptureMetadata | FinalCaptureMetadata = metadata_from_json(
                    metadata_path.read_text(encoding="utf-8")
                )
                self._validate_metadata(metadata=metadata)
                self._validate_directory_metadata(capture_dir=capture_dir, metadata=metadata)
                captures.append(
                    CaptureInventoryItem(
                        invocation_id=metadata.invocation_id,
                        capture_date=metadata.capture_date,
                        path=str(capture_dir),
                        is_complete=marker_path.is_file(),
                        metadata=metadata,
                    )
                )
        captures.sort(key=lambda item: (item.capture_date, item.invocation_id))
        complete_count: int = sum(item.is_complete for item in captures)
        return CaptureInventory(
            captures=tuple(captures),
            complete_count=complete_count,
            incomplete_count=len(captures) - complete_count,
        )

    def close(self) -> None:
        """Close active writers, deliberately leaving their captures incomplete."""

        with self._state_lock:
            captures: tuple[tuple[threading.RLock, dict[ComputeLogStream, BinaryIO]], ...] = tuple(
                (self._locks[invocation_id], writers)
                for invocation_id, writers in self._writers.items()
            )
            self._writers.clear()
            self._locks.clear()
            self._closed = True
        first_error: Exception | None = None
        for lock, writers in captures:
            with lock:
                for writer in writers.values():
                    try:
                        if not writer.closed:
                            writer.flush()
                    except Exception as error:
                        if first_error is None:
                            first_error = error
                    try:
                        if not writer.closed:
                            writer.close()
                    except Exception as error:
                        if first_error is None:
                            first_error = error
                        try:
                            if not writer.closed:
                                writer.close()
                        except Exception as retry_error:
                            if first_error is None:
                                first_error = retry_error
        if first_error is not None:
            raise CaptureStateError("compute log writer cleanup failed") from first_error

    def dispose(self) -> None:
        """Dispose process-local resources without deleting retained logs."""

        self.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        self.close()
        return None

    @overload
    def _find_capture(self, *, invocation_id: str, missing_ok: Literal[False] = False) -> Path: ...

    @overload
    def _find_capture(self, *, invocation_id: str, missing_ok: Literal[True]) -> Path | None: ...

    def _find_capture(self, *, invocation_id: str, missing_ok: bool = False) -> Path | None:
        self._validate_capture_id(invocation_id)
        matches: list[Path] = []
        for date_dir in self._root.iterdir():
            if not _DATE_PATTERN.fullmatch(date_dir.name):
                continue
            self._ensure_not_symlink(path=date_dir)
            self._ensure_contained(path=date_dir)
            if not date_dir.is_dir():
                continue
            candidate: Path = date_dir / invocation_id
            if candidate.is_symlink():
                raise ComputeLogPathError(f"compute log path cannot be a symlink: {candidate}")
            if candidate.exists():
                self._ensure_contained(path=candidate)
                matches.append(candidate)
        if len(matches) > 1:
            raise ComputeLogMetadataError(f"duplicate capture identity {invocation_id!r}")
        if matches:
            return matches[0]
        if missing_ok:
            return None
        raise CaptureNotFoundError(f"capture not found for invocation {invocation_id!r}")

    def _write_metadata(
        self, *, capture_dir: Path, metadata: CaptureMetadata | FinalCaptureMetadata
    ) -> None:
        temporary: Path = capture_dir / f".{METADATA_FILE_NAME}.{uuid4().hex}.tmp"
        destination: Path = capture_dir / METADATA_FILE_NAME
        self._ensure_contained(path=temporary)
        try:
            with temporary.open("x", encoding="utf-8", newline="") as metadata_file:
                metadata_file.write(metadata_to_json(metadata))
                metadata_file.flush()
                os.fsync(metadata_file.fileno())
            os.replace(temporary, destination)
            self._fsync_directory(capture_dir)
        finally:
            temporary.unlink(missing_ok=True)

    def _capture_lock(self, invocation_id: str) -> threading.RLock:
        with self._state_lock:
            try:
                return self._locks[invocation_id]
            except KeyError as error:
                raise CaptureStateError("capture is not active in this storage instance") from error

    def _active_writers(self, invocation_id: str) -> dict[ComputeLogStream, BinaryIO]:
        try:
            return self._writers[invocation_id]
        except KeyError as error:
            raise CaptureStateError("capture is not active in this storage instance") from error

    def _read_byte_counts(self, *, invocation_id: str) -> CaptureByteCounts:
        capture_dir: Path = self._find_capture(invocation_id=invocation_id)
        sizes: dict[ComputeLogStream, int] = {}
        for stream, file_name in _STREAM_FILES.items():
            path: Path = capture_dir / file_name
            self._ensure_contained(path=path)
            sizes[stream] = path.stat().st_size if path.exists() else 0
        return CaptureByteCounts(
            stdout_bytes=sizes[ComputeLogStream.STDOUT],
            stderr_bytes=sizes[ComputeLogStream.STDERR],
            diagnostics_bytes=sizes[ComputeLogStream.DIAGNOSTICS],
        )

    def _validate_directory_metadata(
        self,
        *,
        capture_dir: Path,
        metadata: CaptureMetadata | FinalCaptureMetadata,
    ) -> None:
        if metadata.invocation_id != capture_dir.name:
            raise ComputeLogMetadataError("metadata invocation_id does not match capture directory")
        if metadata.capture_date != capture_dir.parent.name:
            raise ComputeLogMetadataError("metadata capture_date does not match date directory")

    def _validate_metadata(self, metadata: CaptureMetadata | FinalCaptureMetadata) -> None:
        self._validate_capture_id(metadata.invocation_id)
        if metadata.format_version != COMPUTE_LOG_FORMAT_VERSION:
            raise ComputeLogMetadataError("unsupported compute log format version")
        if not metadata.command.strip() or not metadata.project_dir.strip():
            raise ComputeLogMetadataError("command and project_dir must be non-empty")
        if metadata.started_at.tzinfo is None or metadata.started_at.utcoffset() is None:
            raise ComputeLogMetadataError("started_at must be timezone-aware")
        expected_date: str = metadata.started_at.astimezone(UTC).date().isoformat()
        if metadata.capture_date != expected_date:
            raise ComputeLogMetadataError("capture_date must derive from UTC started_at")
        if isinstance(metadata, FinalCaptureMetadata):
            if metadata.completed_at.tzinfo is None or metadata.completed_at < metadata.started_at:
                raise ComputeLogMetadataError(
                    "completed_at must be aware and not precede started_at"
                )
            if type(metadata.exit_code) is not int or any(
                type(count) is not int
                for count in (
                    metadata.stdout_bytes,
                    metadata.stderr_bytes,
                    metadata.diagnostics_bytes,
                )
            ):
                raise ComputeLogMetadataError("exit_code and byte counts must be integers")
            if (
                min(
                    metadata.stdout_bytes,
                    metadata.stderr_bytes,
                    metadata.diagnostics_bytes,
                )
                < 0
            ):
                raise ComputeLogMetadataError("final byte counts must be nonnegative")

    def _validate_capture_id(self, invocation_id: str) -> None:
        if not isinstance(invocation_id, str) or not _CAPTURE_ID_PATTERN.fullmatch(invocation_id):
            raise InvalidCaptureIdError(
                "invocation_id must contain only ASCII letters, digits, underscores, or hyphens"
            )

    def _ensure_contained(self, *, path: Path) -> None:
        resolved: Path = path.resolve(strict=False)
        if not resolved.is_relative_to(self._root):
            raise ComputeLogPathError(f"compute log path escapes configured root: {path}")

    @staticmethod
    def _ensure_not_symlink(*, path: Path) -> None:
        if path.is_symlink():
            raise ComputeLogPathError(f"compute log path cannot be a symlink: {path}")

    def _ensure_open(self) -> None:
        if self._closed:
            raise CaptureStateError("compute log storage is closed")

    @staticmethod
    def _completion_key(item: CaptureInventoryItem) -> tuple[object, str]:
        metadata: CaptureMetadata | FinalCaptureMetadata = item.metadata
        completed_at: object = (
            metadata.completed_at
            if isinstance(metadata, FinalCaptureMetadata)
            else metadata.started_at
        )
        return completed_at, item.invocation_id

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor: int = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
