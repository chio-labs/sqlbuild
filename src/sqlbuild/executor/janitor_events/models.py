"""Immutable records persisted to the janitor audit table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlbuild.executor.janitor_events.types import JanitorEventType


@dataclass(frozen=True)
class JanitorEventRecord:
    """One immutable janitor archive or delete fact."""

    event_id: str
    schema_version: int
    event_type: JanitorEventType
    occurred_at: datetime
    run_id: str
    relation_database: str | None
    relation_schema: str
    relation_type: str | None
    original_name: str | None
    original_qualified_name: str | None
    archive_name: str
    archive_qualified_name: str
    archived_at: datetime
