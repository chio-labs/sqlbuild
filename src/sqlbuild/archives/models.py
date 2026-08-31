"""Logical models for append-only archive state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlbuild.archives.types import ArchiveProvenanceStatus, ArchiveRecordType


@dataclass(frozen=True)
class ArchiveEvent:
    """One immutable archive requirement, completion, or deletion fact."""

    event_id: str
    record_type: ArchiveRecordType
    requirement_id: str
    operation_kind: str
    target_database: str | None
    target_schema: str
    target_name: str
    source_physical_generation: str | None
    archive_name: str
    origin_run_id: str
    execution_run_id: str
    provenance_status: ArchiveProvenanceStatus
    requested_at: datetime
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    archive_physical_generation: str | None = None
    synthetic_reason: str | None = None
    retention_days: int | None = None
    completed_at: datetime | None = None
    observed_at: datetime | None = None


@dataclass(frozen=True)
class ArchiveProjection:
    """Current lifecycle derived from immutable archive events."""

    requirement: ArchiveEvent | None = None
    completion: ArchiveEvent | None = None
    delete_requirement: ArchiveEvent | None = None
    delete_completion: ArchiveEvent | None = None

    @property
    def is_available(self) -> bool:
        return self.completion is not None and self.delete_completion is None

    @property
    def is_deleted(self) -> bool:
        return self.delete_completion is not None


@dataclass(frozen=True)
class ParsedArchiveName:
    """Physical timestamp and readable component parsed from an archive name."""

    archived_at: datetime
    logical_name: str
