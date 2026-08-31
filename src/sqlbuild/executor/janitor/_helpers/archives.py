"""Plan append-only direct janitor archive actions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.archives.classes.direct_store import DirectArchiveEventStore
from sqlbuild.archives.constants import ARCHIVE_EVENT_TABLE_NAME
from sqlbuild.archives.main.archive_event_identity import build_archive_event_id
from sqlbuild.archives.main.archive_requirement_identity import build_archive_requirement_id
from sqlbuild.archives.main.build_archive_name import build_archive_name
from sqlbuild.archives.main.project_archive_events import project_archive_events
from sqlbuild.archives.models import ArchiveEvent, ArchiveProjection
from sqlbuild.archives.types import ArchiveProvenanceStatus, ArchiveRecordType
from sqlbuild.executor.janitor.models import (
    JanitorArchiveCandidate,
    JanitorArchiveDeleteCandidate,
    JanitorDeleteCandidate,
    JanitorRelationKey,
    JanitorSkippedRelation,
    JanitorWarehouseFacts,
)

_ARCHIVE_OPERATION: str = "archive"


def plan_direct_archive_actions(
    *,
    candidates: tuple[JanitorDeleteCandidate, ...],
    facts: JanitorWarehouseFacts,
    adapter: BaseAdapter,
    connection: Any,
    origin_run_id: str,
    archive_retention_days: int,
    now: datetime,
) -> tuple[
    tuple[JanitorArchiveCandidate, ...],
    tuple[JanitorArchiveDeleteCandidate, ...],
    tuple[JanitorSkippedRelation, ...],
]:
    """Plan archive, reconciliation, and permanent deletion actions."""

    histories: tuple[ArchiveEvent, ...] = _read_histories(
        facts=facts, adapter=adapter, connection=connection
    )
    projections: tuple[ArchiveProjection, ...] = _projections(histories)
    physical: dict[JanitorRelationKey, object] = _physical_relations(facts)
    archives: list[JanitorArchiveCandidate] = []
    deletions: list[JanitorArchiveDeleteCandidate] = []
    skipped: list[JanitorSkippedRelation] = []
    pending_targets: set[JanitorRelationKey] = set()
    for projection in projections:
        requirement: ArchiveEvent | None = projection.requirement
        if requirement is None:
            continue
        origin_key: JanitorRelationKey = _origin_key(requirement)
        archive_key: JanitorRelationKey = _archive_key(requirement)
        if projection.completion is None:
            pending_targets.add(origin_key)
            archive_action, archive_skip = _plan_archive_recovery(
                projection=projection,
                physical=physical,
                adapter=adapter,
                connection=connection,
            )
            if archive_action is not None:
                archives.append(archive_action)
            if archive_skip is not None:
                skipped.append(archive_skip)
            continue
        delete_action, delete_skip = _plan_archive_deletion(
            projection=projection,
            archive_key=archive_key,
            physical=physical,
            adapter=adapter,
            connection=connection,
            archive_retention_days=archive_retention_days,
            now=now,
        )
        if delete_action is not None:
            deletions.append(delete_action)
        if delete_skip is not None:
            skipped.append(delete_skip)
    for candidate in candidates:
        if candidate.key in pending_targets:
            continue
        requirement: ArchiveEvent = _new_requirement(
            candidate=candidate,
            adapter=adapter,
            connection=connection,
            origin_run_id=origin_run_id,
            archive_retention_days=archive_retention_days,
            now=now,
        )
        archives.append(
            JanitorArchiveCandidate(
                origin_key=candidate.key,
                archive_key=_archive_key(requirement),
                requirement=requirement,
            )
        )
    return tuple(archives), tuple(deletions), tuple(skipped)


def _read_histories(
    *, facts: JanitorWarehouseFacts, adapter: BaseAdapter, connection: Any
) -> tuple[ArchiveEvent, ...]:
    store: DirectArchiveEventStore = DirectArchiveEventStore(adapter=adapter, connection=connection)
    events: list[ArchiveEvent] = []
    for schema_key, relations in facts.relations_by_schema.items():
        if schema_key[1] is None or not any(
            relation.name == ARCHIVE_EVENT_TABLE_NAME for relation in relations
        ):
            continue
        events.extend(store.read_schema_history(database=schema_key[0], schema=schema_key[1]))
    return tuple(events)


def _projections(events: tuple[ArchiveEvent, ...]) -> tuple[ArchiveProjection, ...]:
    grouped: dict[str, list[ArchiveEvent]] = {}
    for event in events:
        grouped.setdefault(event.requirement_id, []).append(event)
    return tuple(project_archive_events(tuple(group)) for group in grouped.values())


def _physical_relations(facts: JanitorWarehouseFacts) -> dict[JanitorRelationKey, object]:
    physical: dict[JanitorRelationKey, object] = {}
    for relations in facts.relations_by_schema.values():
        for relation in relations:
            physical[JanitorRelationKey(relation.database, relation.schema, relation.name)] = (
                relation
            )
    return physical


def _plan_archive_recovery(
    *,
    projection: ArchiveProjection,
    physical: dict[JanitorRelationKey, object],
    adapter: BaseAdapter,
    connection: Any,
) -> tuple[JanitorArchiveCandidate | None, JanitorSkippedRelation | None]:
    requirement: ArchiveEvent = cast(ArchiveEvent, projection.requirement)
    origin_key: JanitorRelationKey = _origin_key(requirement)
    archive_key: JanitorRelationKey = _archive_key(requirement)
    origin_exists: bool = origin_key in physical
    archive_exists: bool = archive_key in physical
    if origin_exists and archive_exists:
        return None, JanitorSkippedRelation(
            key=origin_key, reason="archive requirement has both origin and archive present"
        )
    if origin_exists:
        generation: str | None = _generation(adapter=adapter, connection=connection, key=origin_key)
        if _conflicts(expected=requirement.source_physical_generation, observed=generation):
            return None, JanitorSkippedRelation(
                key=origin_key, reason="archive source generation conflicts with requirement"
            )
        return JanitorArchiveCandidate(origin_key, archive_key, requirement), None
    if archive_exists:
        return JanitorArchiveCandidate(
            origin_key, archive_key, requirement, rename_required=False
        ), None
    return None, None


def _plan_archive_deletion(
    *,
    projection: ArchiveProjection,
    archive_key: JanitorRelationKey,
    physical: dict[JanitorRelationKey, object],
    adapter: BaseAdapter,
    connection: Any,
    archive_retention_days: int,
    now: datetime,
) -> tuple[JanitorArchiveDeleteCandidate | None, JanitorSkippedRelation | None]:
    completion: ArchiveEvent = cast(ArchiveEvent, projection.completion)
    requirement: ArchiveEvent = cast(ArchiveEvent, projection.requirement)
    archive_exists: bool = archive_key in physical
    if projection.delete_completion is not None:
        return None, None
    expected_generation: str | None = completion.archive_physical_generation
    if projection.delete_requirement is not None:
        if archive_exists and _conflicts(
            expected=expected_generation,
            observed=_generation(adapter=adapter, connection=connection, key=archive_key),
        ):
            return None, JanitorSkippedRelation(
                key=archive_key, reason="archive generation conflicts with completion"
            )
        return JanitorArchiveDeleteCandidate(
            archive_key,
            requirement,
            expected_generation,
            drop_required=archive_exists,
            delete_requirement=projection.delete_requirement,
        ), None
    completed_at: datetime = _aware(completion.completed_at or completion.requested_at)
    if completed_at > now - timedelta(days=archive_retention_days):
        return None, None
    if not archive_exists:
        return None, None
    current_generation: str | None = _generation(
        adapter=adapter, connection=connection, key=archive_key
    )
    if (
        expected_generation is None
        or current_generation is None
        or expected_generation != current_generation
    ):
        return None, JanitorSkippedRelation(
            key=archive_key, reason="archive physical generation is not proven"
        )
    return JanitorArchiveDeleteCandidate(archive_key, requirement, expected_generation), None


def _new_requirement(
    *,
    candidate: JanitorDeleteCandidate,
    adapter: BaseAdapter,
    connection: Any,
    origin_run_id: str,
    archive_retention_days: int,
    now: datetime,
) -> ArchiveEvent:
    source_generation: str | None = _generation(
        adapter=adapter, connection=connection, key=candidate.key
    )
    archive_name: str = build_archive_name(
        logical_name=candidate.key.name,
        archived_at=now,
        identifier_limit=adapter.maximum_identifier_length(),
    )
    requirement_id: str = build_archive_requirement_id(
        operation_kind=_ARCHIVE_OPERATION,
        target_database=candidate.key.database,
        target_schema=candidate.key.schema or "",
        target_name=candidate.key.name,
        source_physical_generation=source_generation,
        archive_name=archive_name,
    )
    return ArchiveEvent(
        event_id=build_archive_event_id(
            requirement_id=requirement_id, record_type=ArchiveRecordType.REQUIREMENT
        ),
        record_type=ArchiveRecordType.REQUIREMENT,
        requirement_id=requirement_id,
        operation_kind=_ARCHIVE_OPERATION,
        target_database=candidate.key.database,
        target_schema=candidate.key.schema or "",
        target_name=candidate.key.name,
        source_physical_generation=source_generation,
        archive_name=archive_name,
        origin_run_id=origin_run_id,
        execution_run_id=origin_run_id,
        provenance_status=ArchiveProvenanceStatus.KNOWN
        if source_generation is not None
        else ArchiveProvenanceStatus.UNKNOWN,
        requested_at=now,
        retention_days=archive_retention_days,
    )


def _origin_key(event: ArchiveEvent) -> JanitorRelationKey:
    return JanitorRelationKey(event.target_database, event.target_schema, event.target_name)


def _archive_key(event: ArchiveEvent) -> JanitorRelationKey:
    return JanitorRelationKey(event.target_database, event.target_schema, event.archive_name)


def _generation(*, adapter: BaseAdapter, connection: Any, key: JanitorRelationKey) -> str | None:
    return adapter.physical_relation_generation(
        connection=connection,
        database=key.database,
        schema=key.schema,
        name=key.name,
    )


def _conflicts(*, expected: str | None, observed: str | None) -> bool:
    return expected is not None and observed is not None and expected != observed


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
