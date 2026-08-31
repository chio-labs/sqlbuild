"""Stable encoding for append-only archive events."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.archives.constants import ARCHIVE_EVENT_COLUMNS
from sqlbuild.archives.models import ArchiveEvent
from sqlbuild.archives.types import ArchiveProvenanceStatus, ArchiveRecordType


class ArchiveEventCodec:
    """Encode and decode archive facts in stable column order."""

    @staticmethod
    def values(event: ArchiveEvent) -> tuple[object | None, ...]:
        return (
            event.event_id,
            event.record_type.value,
            event.requirement_id,
            event.operation_kind,
            event.target_database,
            event.target_schema,
            event.target_name,
            event.source_physical_generation,
            event.archive_name,
            event.archive_physical_generation,
            event.origin_run_id,
            event.execution_run_id,
            event.provenance_status.value,
            event.synthetic_reason,
            event.retention_days,
            event.requested_at,
            event.completed_at,
            event.observed_at,
            event.created_at,
        )

    @staticmethod
    def from_row(row: tuple[Any, ...]) -> ArchiveEvent:
        values: dict[str, Any] = dict(zip(ARCHIVE_EVENT_COLUMNS, row, strict=True))
        return ArchiveEvent(
            event_id=str(values["event_id"]),
            record_type=ArchiveRecordType(values["record_type"]),
            requirement_id=str(values["requirement_id"]),
            operation_kind=str(values["operation_kind"]),
            target_database=_optional_str(values["target_database"]),
            target_schema=str(values["target_schema"]),
            target_name=str(values["target_name"]),
            source_physical_generation=_optional_str(values["source_physical_generation"]),
            archive_name=str(values["archive_name"]),
            archive_physical_generation=_optional_str(values["archive_physical_generation"]),
            origin_run_id=str(values["origin_run_id"]),
            execution_run_id=str(values["execution_run_id"]),
            provenance_status=ArchiveProvenanceStatus(values["provenance_status"]),
            synthetic_reason=_optional_str(values["synthetic_reason"]),
            retention_days=_optional_int(values["retention_days"]),
            requested_at=_datetime(values["requested_at"]),
            completed_at=_optional_datetime(values["completed_at"]),
            observed_at=_optional_datetime(values["observed_at"]),
            created_at=_datetime(values["created_at"]),
        )


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: object) -> int | None:
    return None if value is None else int(str(value))


def _datetime(value: object) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def _optional_datetime(value: object) -> datetime | None:
    return None if value is None else _datetime(value)
