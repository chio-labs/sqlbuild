"""Deterministic archive requirement and event identities."""

from __future__ import annotations

import hashlib
import json

from sqlbuild.archives.types import ArchiveRecordType


def archive_requirement_id(
    *,
    operation_kind: str,
    target_database: str | None,
    target_schema: str,
    target_name: str,
    source_physical_generation: str | None,
    archive_name: str,
) -> str:
    """Return a stable requirement ID for one source incarnation and archive name."""

    return _digest(
        (
            operation_kind,
            target_database,
            target_schema,
            target_name,
            source_physical_generation,
            archive_name,
        )
    )


def archive_event_id(*, requirement_id: str, record_type: ArchiveRecordType) -> str:
    """Return a stable ID for one immutable lifecycle fact."""

    return _digest((requirement_id, record_type.value))


def _digest(values: tuple[object, ...]) -> str:
    encoded: str = json.dumps(values, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode()).hexdigest()
