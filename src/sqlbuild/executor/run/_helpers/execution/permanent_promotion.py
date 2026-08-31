"""Permanent table promotion with append-only safety archives."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.archives.classes.direct_store import DirectArchiveEventStore
from sqlbuild.archives.exceptions import ArchiveStateError
from sqlbuild.archives.main.archive_event_identity import build_archive_event_id
from sqlbuild.archives.main.archive_requirement_identity import build_archive_requirement_id
from sqlbuild.archives.main.build_archive_name import build_archive_name
from sqlbuild.archives.main.project_archive_events import project_archive_events
from sqlbuild.archives.models import ArchiveEvent, ArchiveProjection
from sqlbuild.archives.types import ArchiveProvenanceStatus, ArchiveRecordType
from sqlbuild.compiler.planner.models import ModelPlanEntry

_TABLE_TYPE_MIGRATION_OPERATION: str = "table_type_migration"


def build_permanent_promotion_requirement(
    *,
    adapter: BaseAdapter,
    target: RelationInfo,
    target_database: str | None,
    target_schema: str,
    target_name: str,
    operation_identity: str,
) -> ArchiveEvent:
    """Build the deterministic safety-archive requirement for one target generation."""

    generation: str = _required_generation(relation=target, label=target_name)
    created_at: datetime = _required_created_at(relation=target, label=target_name)
    archive_name: str = build_archive_name(
        logical_name=target_name,
        archived_at=created_at,
        identifier_limit=adapter.maximum_identifier_length(),
    )
    requirement_id: str = build_archive_requirement_id(
        operation_kind=_TABLE_TYPE_MIGRATION_OPERATION,
        target_database=target_database,
        target_schema=target_schema,
        target_name=target_name,
        source_physical_generation=generation,
        archive_name=archive_name,
    )
    return ArchiveEvent(
        event_id=build_archive_event_id(
            requirement_id=requirement_id, record_type=ArchiveRecordType.REQUIREMENT
        ),
        record_type=ArchiveRecordType.REQUIREMENT,
        requirement_id=requirement_id,
        operation_kind=_TABLE_TYPE_MIGRATION_OPERATION,
        target_database=target_database,
        target_schema=target_schema,
        target_name=target_name,
        source_physical_generation=generation,
        archive_name=archive_name,
        origin_run_id=operation_identity,
        execution_run_id=operation_identity,
        provenance_status=ArchiveProvenanceStatus.KNOWN,
        requested_at=created_at,
        created_at=created_at,
    )


def promote_permanent_relation(
    *,
    adapter: BaseAdapter,
    connection: Any,
    staging_relation: str,
    staging_name: str,
    destination_relation: str,
    destination_database: str | None,
    destination_schema: str | None,
    destination_name: str,
    operation_identity: str,
    statement_recorder: StatementRecorder,
) -> None:
    """Archive an existing generation and promote an exclusive permanent staging table."""

    if destination_schema is None:
        raise ArchiveStateError("permanent table promotion requires a destination schema")
    store: DirectArchiveEventStore = DirectArchiveEventStore(adapter=adapter, connection=connection)
    history: tuple[ArchiveEvent, ...] = store.read_target_history(
        database=destination_database,
        schema=destination_schema,
        target_name=destination_name,
    )
    target: RelationInfo | None = _inspect_relation(
        adapter=adapter,
        connection=connection,
        database=destination_database,
        schema=destination_schema,
        name=destination_name,
    )
    previous: ArchiveEvent | None = _latest_migration_requirement(history=history)
    if previous is not None:
        previous_projection: ArchiveProjection = _projection_from_history(
            history=history, requirement=previous
        )
        previous_archive: RelationInfo | None = _inspect_event_relation(
            adapter=adapter,
            connection=connection,
            event=previous,
            name=previous.archive_name,
        )
        staging: RelationInfo | None = _inspect_relation(
            adapter=adapter,
            connection=connection,
            database=destination_database,
            schema=destination_schema,
            name=staging_name,
        )
        if (
            target is not None
            and target.is_transient is False
            and previous_projection.completion is not None
            and previous.origin_run_id == operation_identity
            and previous_archive is not None
            and _generation(previous_archive)
            == previous_projection.completion.archive_physical_generation
        ):
            if staging is not None:
                adapter.drop(
                    connection=connection,
                    destination=staging_relation,
                    if_exists=True,
                    statement_recorder=statement_recorder,
                )
            return
        if target is None:
            archive_relation: str | None = adapter.render_qualified_name(
                database=destination_database,
                schema=destination_schema,
                name=previous.archive_name,
            )
            if archive_relation is None:
                raise ArchiveStateError("permanent table promotion could not qualify the archive")
            _reconcile_archive(
                adapter=adapter,
                connection=connection,
                store=store,
                requirement=previous,
                target_relation=destination_relation,
                archive_relation=archive_relation,
                statement_recorder=statement_recorder,
            )
            _promote_and_verify(
                adapter=adapter,
                connection=connection,
                staging_relation=staging_relation,
                staging_name=staging_name,
                destination_relation=destination_relation,
                destination_database=destination_database,
                destination_schema=destination_schema,
                destination_name=destination_name,
                statement_recorder=statement_recorder,
            )
            return
    if target is None:
        _promote_and_verify(
            adapter=adapter,
            connection=connection,
            staging_relation=staging_relation,
            staging_name=staging_name,
            destination_relation=destination_relation,
            destination_database=destination_database,
            destination_schema=destination_schema,
            destination_name=destination_name,
            statement_recorder=statement_recorder,
        )
        return

    requirement: ArchiveEvent = build_permanent_promotion_requirement(
        adapter=adapter,
        target=target,
        target_database=destination_database,
        target_schema=destination_schema,
        target_name=destination_name,
        operation_identity=operation_identity,
    )
    archive_relation: str | None = adapter.render_qualified_name(
        database=destination_database,
        schema=destination_schema,
        name=requirement.archive_name,
    )
    if archive_relation is None:
        raise ArchiveStateError("permanent table promotion could not qualify the archive")
    projection: ArchiveProjection = _projection(store=store, requirement=requirement)
    _enforce_existing_requirement(projection=projection, expected=requirement)
    store.write(requirement)
    _reconcile_archive(
        adapter=adapter,
        connection=connection,
        store=store,
        requirement=requirement,
        target_relation=destination_relation,
        archive_relation=archive_relation,
        statement_recorder=statement_recorder,
    )
    _promote_and_verify(
        adapter=adapter,
        connection=connection,
        staging_relation=staging_relation,
        staging_name=staging_name,
        destination_relation=destination_relation,
        destination_database=destination_database,
        destination_schema=destination_schema,
        destination_name=destination_name,
        statement_recorder=statement_recorder,
    )


def _reconcile_archive(
    *,
    adapter: BaseAdapter,
    connection: Any,
    store: DirectArchiveEventStore,
    requirement: ArchiveEvent,
    target_relation: str,
    archive_relation: str,
    statement_recorder: StatementRecorder,
) -> None:
    target: RelationInfo | None = _inspect_event_relation(
        adapter=adapter, connection=connection, event=requirement, name=requirement.target_name
    )
    archive: RelationInfo | None = _inspect_event_relation(
        adapter=adapter, connection=connection, event=requirement, name=requirement.archive_name
    )
    expected_generation: str | None = requirement.source_physical_generation
    if target is not None and _generation(target) != expected_generation:
        raise ArchiveStateError("Target physical generation changed before safety archive")
    if archive is not None and _generation(archive) != expected_generation:
        raise ArchiveStateError("Archive physical generation conflicts with safety requirement")
    if target is not None and archive is not None:
        raise ArchiveStateError("Target and safety archive both contain the source generation")
    if target is None and archive is None:
        raise ArchiveStateError("Target and safety archive are both absent after requirement")
    if target is not None:
        adapter.rename(
            connection=connection,
            origin=target_relation,
            destination=archive_relation,
            statement_recorder=statement_recorder,
        )
    verified_archive: RelationInfo | None = _inspect_event_relation(
        adapter=adapter, connection=connection, event=requirement, name=requirement.archive_name
    )
    if verified_archive is None or _generation(verified_archive) != expected_generation:
        raise ArchiveStateError("Safety archive generation was not proven after rename")
    completed_at: datetime = _required_last_altered_at(
        relation=verified_archive, label=requirement.archive_name
    )
    completion: ArchiveEvent = replace(
        requirement,
        event_id=build_archive_event_id(
            requirement_id=requirement.requirement_id,
            record_type=ArchiveRecordType.COMPLETION,
        ),
        record_type=ArchiveRecordType.COMPLETION,
        archive_physical_generation=expected_generation,
        completed_at=completed_at,
        observed_at=completed_at,
        created_at=completed_at,
    )
    projection: ArchiveProjection = _projection(store=store, requirement=requirement)
    if projection.completion is not None and projection.completion != completion:
        raise ArchiveStateError("Safety archive completion has a conflicting payload")
    store.write(completion)
    persisted: ArchiveProjection = _projection(store=store, requirement=requirement)
    if persisted.completion != completion:
        raise ArchiveStateError("Safety archive completion was not persisted")


def _promote_and_verify(
    *,
    adapter: BaseAdapter,
    connection: Any,
    staging_relation: str,
    staging_name: str,
    destination_relation: str,
    destination_database: str | None,
    destination_schema: str,
    destination_name: str,
    statement_recorder: StatementRecorder,
) -> None:
    staging: RelationInfo | None = _inspect_relation(
        adapter=adapter,
        connection=connection,
        database=destination_database,
        schema=destination_schema,
        name=staging_name,
    )
    target: RelationInfo | None = _inspect_relation(
        adapter=adapter,
        connection=connection,
        database=destination_database,
        schema=destination_schema,
        name=destination_name,
    )
    if target is not None:
        if target.is_transient is False and staging is None:
            return
        raise ArchiveStateError("Target reappeared before permanent staging promotion")
    if staging is None or staging.is_transient is not False:
        raise ArchiveStateError("Permanent staging generation is absent or transient")
    adapter.rename(
        connection=connection,
        origin=staging_relation,
        destination=destination_relation,
        statement_recorder=statement_recorder,
    )
    promoted: RelationInfo | None = _inspect_relation(
        adapter=adapter,
        connection=connection,
        database=destination_database,
        schema=destination_schema,
        name=destination_name,
    )
    if promoted is None or promoted.is_transient is not False:
        raise ArchiveStateError("Promoted target is not a proven permanent table")


def _projection(*, store: DirectArchiveEventStore, requirement: ArchiveEvent) -> ArchiveProjection:
    history: tuple[ArchiveEvent, ...] = store.read_target_history(
        database=requirement.target_database,
        schema=requirement.target_schema,
        target_name=requirement.target_name,
    )
    return _projection_from_history(history=history, requirement=requirement)


def _projection_from_history(
    *, history: tuple[ArchiveEvent, ...], requirement: ArchiveEvent
) -> ArchiveProjection:
    matching: tuple[ArchiveEvent, ...] = tuple(
        event for event in history if event.requirement_id == requirement.requirement_id
    )
    return project_archive_events(matching)


def _latest_migration_requirement(*, history: tuple[ArchiveEvent, ...]) -> ArchiveEvent | None:
    requirements: tuple[ArchiveEvent, ...] = tuple(
        event
        for event in history
        if event.operation_kind == _TABLE_TYPE_MIGRATION_OPERATION
        and event.record_type == ArchiveRecordType.REQUIREMENT
    )
    return max(requirements, key=lambda event: (event.created_at, event.event_id), default=None)


def _enforce_existing_requirement(*, projection: ArchiveProjection, expected: ArchiveEvent) -> None:
    if projection.requirement is not None and projection.requirement != expected:
        raise ArchiveStateError("Safety archive requirement has a conflicting payload")


def _inspect_event_relation(
    *, adapter: BaseAdapter, connection: Any, event: ArchiveEvent, name: str
) -> RelationInfo | None:
    return _inspect_relation(
        adapter=adapter,
        connection=connection,
        database=event.target_database,
        schema=event.target_schema,
        name=name,
    )


def _inspect_relation(
    *,
    adapter: BaseAdapter,
    connection: Any,
    database: str | None,
    schema: str,
    name: str,
) -> RelationInfo | None:
    relations: tuple[RelationInfo, ...] = adapter.list_relations(
        connection=connection, database=database, schemas=(schema,), names=(name,)
    )
    if len(relations) > 1:
        raise ArchiveStateError(f"Relation metadata is ambiguous for {schema}.{name}")
    return relations[0] if relations else None


def _required_created_at(*, relation: RelationInfo, label: str) -> datetime:
    if relation.created_at is None:
        raise ArchiveStateError(f"Stable physical generation is unavailable for {label}")
    return _as_utc(relation.created_at)


def _required_last_altered_at(*, relation: RelationInfo, label: str) -> datetime:
    if relation.last_altered_at is None:
        raise ArchiveStateError(f"Stable archive completion time is unavailable for {label}")
    return _as_utc(relation.last_altered_at)


def _required_generation(*, relation: RelationInfo, label: str) -> str:
    return _required_created_at(relation=relation, label=label).isoformat()


def _generation(relation: RelationInfo) -> str | None:
    return None if relation.created_at is None else _as_utc(relation.created_at).isoformat()


def permanent_model_identity(entry: ModelPlanEntry) -> str:
    """Return the durable model identity used for an operation-owned staging name."""

    if entry.fingerprint_version_hash:
        return entry.fingerprint_version_hash
    payload: str = "\x00".join(
        (
            entry.name,
            entry.destination.qualified_name or "",
            entry.fingerprint_query_sql,
            entry.resolved_sql,
        )
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def permanent_operation_identity(*, entry: ModelPlanEntry, run_id: str) -> str:
    """Return an identity stable across retries of one build run."""

    payload: str = f"{permanent_model_identity(entry)}\x00{run_id}"
    return sha256(payload.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
