from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlbuild.archives.models import ArchiveEvent


@dataclass(frozen=True)
class ArchiveNameTestCase:
    description: str
    logical_name: str
    archived_at: datetime
    identifier_limit: int
    expected_name: str


@dataclass(frozen=True)
class ArchiveProjectionTestCase:
    description: str
    events: tuple[ArchiveEvent, ...]
    expected_available: bool
    expected_deleted: bool
    expected_completion_event_id: str | None


@dataclass(frozen=True)
class ArchiveSqlTestCase:
    description: str
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...]


@dataclass(frozen=True)
class ArchiveParseTestCase:
    description: str
    name: str
    expected_archived_at: datetime
    expected_logical_name: str


@dataclass(frozen=True)
class ArchiveIdentityTestCase:
    description: str
    operation_kind: str
    target_database: str | None
    target_schema: str
    target_name: str
    source_physical_generation: str | None
    archive_name: str
    expected_stable: bool
    expected_event_types_distinct: bool


@dataclass(frozen=True)
class ArchiveConflictTestCase:
    description: str
    events: tuple[ArchiveEvent, ...]
    expected_error_fragment: str


@dataclass(frozen=True)
class ArchiveRenderedSqlTestCase:
    description: str
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...]
