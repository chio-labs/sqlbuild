"""Immutable compute log metadata and operation results."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlbuild.runtime.compute_logs.types import ByteCursor, ComputeLogStream


@dataclass(frozen=True)
class CaptureMetadata:
    """Safe metadata recorded before stream capture starts."""

    format_version: int
    invocation_id: str
    command: str
    project_dir: str
    started_at: datetime
    capture_date: str
    target: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class FinalCaptureMetadata:
    """Metadata atomically published before capture completion evidence."""

    format_version: int
    invocation_id: str
    command: str
    project_dir: str
    started_at: datetime
    capture_date: str
    completed_at: datetime
    exit_code: int
    stdout_bytes: int
    stderr_bytes: int
    diagnostics_bytes: int
    target: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class ComputeLogReadChunk:
    """One raw stream chunk addressed by an exclusive byte cursor."""

    data: bytes
    next_cursor: ByteCursor
    is_complete: bool


@dataclass(frozen=True)
class CaptureInventoryItem:
    """One capture visible beneath a compute log root."""

    invocation_id: str
    capture_date: str
    path: str
    is_complete: bool
    metadata: CaptureMetadata | FinalCaptureMetadata


@dataclass(frozen=True)
class CaptureInventory:
    """Deterministically ordered captures and aggregate state counts."""

    captures: tuple[CaptureInventoryItem, ...]
    complete_count: int
    incomplete_count: int


@dataclass(frozen=True)
class PruneResult:
    """Captures removed or retained by one bounded retention pass."""

    deleted_invocation_ids: tuple[str, ...]
    retained_complete_count: int
    retained_incomplete_count: int


@dataclass(frozen=True)
class StreamByteCount:
    """Current byte count for one compute log stream."""

    stream: ComputeLogStream
    byte_count: int


@dataclass(frozen=True)
class CaptureByteCounts:
    """Atomic snapshot of all stream byte counts for one active capture."""

    stdout_bytes: int
    stderr_bytes: int
    diagnostics_bytes: int
