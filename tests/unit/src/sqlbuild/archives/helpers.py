from __future__ import annotations

from datetime import UTC, datetime

from sqlbuild.adapter.contract.types import FrameworkType
from sqlbuild.archives.models import ArchiveEvent
from sqlbuild.archives.types import ArchiveProvenanceStatus, ArchiveRecordType


def archive_event(
    *,
    event_id: str,
    record_type: ArchiveRecordType,
    requirement_id: str = "requirement-1",
    created_at: datetime | None = None,
    archive_physical_generation: str | None = None,
    completed_at: datetime | None = None,
) -> ArchiveEvent:
    return ArchiveEvent(
        event_id=event_id,
        record_type=record_type,
        requirement_id=requirement_id,
        operation_kind="table_type_migration",
        target_database="warehouse",
        target_schema="analytics",
        target_name="orders",
        source_physical_generation="generation-1",
        archive_name="__sqb_archive__20260831T142530123456Z__orders",
        archive_physical_generation=archive_physical_generation,
        origin_run_id="run-1",
        execution_run_id="run-1",
        provenance_status=ArchiveProvenanceStatus.KNOWN,
        requested_at=datetime(2026, 8, 31, 14, 25, 30, 123456, tzinfo=UTC),
        completed_at=completed_at,
        created_at=created_at or datetime(2026, 8, 31, 14, 25, 30, tzinfo=UTC),
    )


def qualified_name(*, database: str | None, schema: str | None, name: str) -> str:
    return f"{database}.{schema}.{name}"


def framework_type(framework_type_value: FrameworkType) -> str:
    return {
        FrameworkType.STRING: "TEXT",
        FrameworkType.TIMESTAMP: "TIMESTAMP",
    }[framework_type_value]
