"""Execute direct archive actions through append-only facts."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.archives.classes.direct_store import DirectArchiveEventStore
from sqlbuild.archives.exceptions import ArchiveStateError
from sqlbuild.archives.main.archive_event_identity import build_archive_event_id
from sqlbuild.archives.models import ArchiveEvent
from sqlbuild.archives.types import ArchiveProvenanceStatus, ArchiveRecordType
from sqlbuild.executor.janitor.models import (
    JanitorArchiveCandidate,
    JanitorArchiveDeleteCandidate,
    JanitorRelationKey,
)


def apply_archive_actions(
    *,
    candidates: tuple[JanitorArchiveCandidate, ...],
    adapter: BaseAdapter,
    connection: Any,
    recorder: StatementRecorder,
) -> tuple[JanitorArchiveCandidate, ...]:
    store: DirectArchiveEventStore = DirectArchiveEventStore(adapter=adapter, connection=connection)
    for candidate in candidates:
        store.write(candidate.requirement)
        if candidate.rename_required:
            observed: str | None = _generation(
                adapter=adapter, connection=connection, key=candidate.origin_key
            )
            _enforce_no_conflict(
                expected=candidate.requirement.source_physical_generation,
                observed=observed,
                label=candidate.origin_key.display_name(),
            )
            adapter.rename(
                connection=connection,
                origin=candidate.origin_key.display_name(),
                destination=candidate.archive_key.display_name(),
                statement_recorder=recorder,
            )
        archive_generation: str | None = _generation(
            adapter=adapter, connection=connection, key=candidate.archive_key
        )
        completion: ArchiveEvent = replace(
            candidate.requirement,
            event_id=build_archive_event_id(
                requirement_id=candidate.requirement.requirement_id,
                record_type=ArchiveRecordType.COMPLETION,
            ),
            record_type=ArchiveRecordType.COMPLETION,
            archive_physical_generation=archive_generation,
            provenance_status=(
                ArchiveProvenanceStatus.KNOWN
                if archive_generation is not None
                else ArchiveProvenanceStatus.UNKNOWN
            ),
            completed_at=datetime.now(UTC),
            observed_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        store.write(completion)
    return candidates


def apply_archive_deletions(
    *,
    candidates: tuple[JanitorArchiveDeleteCandidate, ...],
    adapter: BaseAdapter,
    connection: Any,
    recorder: StatementRecorder,
) -> tuple[JanitorArchiveDeleteCandidate, ...]:
    store: DirectArchiveEventStore = DirectArchiveEventStore(adapter=adapter, connection=connection)
    for candidate in candidates:
        requested_at: datetime = datetime.now(UTC)
        delete_requirement: ArchiveEvent = candidate.delete_requirement or replace(
            candidate.requirement,
            event_id=build_archive_event_id(
                requirement_id=candidate.requirement.requirement_id,
                record_type=ArchiveRecordType.DELETE_REQUIREMENT,
            ),
            record_type=ArchiveRecordType.DELETE_REQUIREMENT,
            requested_at=requested_at,
            completed_at=None,
            observed_at=requested_at,
            created_at=requested_at,
        )
        store.write(delete_requirement)
        if candidate.drop_required:
            observed: str | None = _generation(
                adapter=adapter, connection=connection, key=candidate.archive_key
            )
            if candidate.archive_physical_generation is None or observed is None:
                raise ArchiveStateError(
                    f"Archive generation is not proven for {candidate.archive_key.display_name()}"
                )
            _enforce_no_conflict(
                expected=candidate.archive_physical_generation,
                observed=observed,
                label=candidate.archive_key.display_name(),
            )
            adapter.drop(
                connection=connection,
                destination=candidate.archive_key.display_name(),
                if_exists=True,
                statement_recorder=recorder,
            )
        completed_at: datetime = datetime.now(UTC)
        store.write(
            replace(
                candidate.requirement,
                event_id=build_archive_event_id(
                    requirement_id=candidate.requirement.requirement_id,
                    record_type=ArchiveRecordType.DELETE_COMPLETION,
                ),
                record_type=ArchiveRecordType.DELETE_COMPLETION,
                requested_at=delete_requirement.requested_at,
                completed_at=completed_at,
                observed_at=completed_at,
                created_at=completed_at,
            )
        )
    return candidates


def _generation(*, adapter: BaseAdapter, connection: Any, key: JanitorRelationKey) -> str | None:
    return adapter.physical_relation_generation(
        connection=connection,
        database=key.database,
        schema=key.schema,
        name=key.name,
    )


def _enforce_no_conflict(*, expected: str | None, observed: str | None, label: str) -> None:
    if expected is not None and observed is not None and expected != observed:
        raise ArchiveStateError(f"Physical generation changed for {label}")
