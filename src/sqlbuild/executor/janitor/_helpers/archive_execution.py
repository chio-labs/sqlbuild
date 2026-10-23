"""Direct-mode janitor archive renames, archive drops, and audit events."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.types import RelationType
from sqlbuild.adapter.relations.main.resolve_qualified_name_parts import (
    resolve_qualified_name_parts,
)
from sqlbuild.adapter.type_system.main.normalize_relation_type import normalize_relation_type
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.janitor.classes.janitor_workers import JanitorWorkers
from sqlbuild.executor.janitor.constants import ARCHIVE_NAME_SEPARATOR
from sqlbuild.executor.janitor.main._run_janitor_phase import run_janitor_phase
from sqlbuild.executor.janitor.models import (
    JanitorActionDone,
    JanitorArchiveCandidate,
    JanitorArchivedRelation,
    JanitorPlan,
    JanitorProgressItem,
    JanitorRelationKey,
)
from sqlbuild.executor.janitor.types import JanitorAction, JanitorPhase, JanitorProgress
from sqlbuild.executor.janitor_events.classes.janitor_event_writer import JanitorEventWriter
from sqlbuild.executor.janitor_events.constants import (
    JANITOR_EVENT_CHUNK_SIZE,
    JANITOR_EVENT_SCHEMA_VERSION,
)
from sqlbuild.executor.janitor_events.main.janitor_event_id import build_janitor_event_id
from sqlbuild.executor.janitor_events.models import JanitorEventRecord
from sqlbuild.executor.janitor_events.types import JanitorEventType
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle
from sqlbuild.runtime.observability.main.current_execution_identity import (
    current_execution_identity,
)
from sqlbuild.runtime.observability.models import ExecutionIdentity


def janitor_run_id() -> str:
    """Return the invocation identity used to group janitor audit events."""

    identity: ExecutionIdentity | None = current_execution_identity()
    return identity.invocation_id if identity is not None else uuid4().hex


def apply_direct_archives(
    *,
    plan: JanitorPlan,
    adapter: BaseAdapter,
    workers: JanitorWorkers,
    recorder: StatementRecorder,
    run_id: str,
    progress: JanitorProgress | None = None,
) -> tuple[tuple[JanitorArchiveCandidate, ...], tuple[JanitorArchivedRelation, ...]]:
    """Rename stale relations to archives, then drop expired archives, auditing each chunk."""

    schemas: tuple[tuple[str | None, str], ...] = _create_event_tables(
        adapter=adapter, connection=workers.connection, plan=plan
    )
    events: JanitorEventWriter = JanitorEventWriter(
        execute=adapter.execute,
        render_qualified_name=adapter.render_qualified_name,
        run_id=run_id,
    )
    if schemas:
        events.read_existing(connection=workers.connection, schemas=schemas)

    def archive_relation(*, item: JanitorArchiveCandidate, connection: Any) -> JanitorActionDone:
        with OperationLifecycle(operation_kind="janitor", operation_name="janitor_cleanup_action"):
            _rename_relation(
                adapter=adapter,
                connection=connection,
                candidate=item,
                recorder=recorder,
            )
        record: JanitorEventRecord = _event_record(
            adapter=adapter,
            event_type=JanitorEventType.ARCHIVE,
            run_id=run_id,
            archive=JanitorArchivedRelation(
                key=item.archive_key,
                relation_type=item.relation.relation_type,
                archived_at=item.archived_at,
                expires_at=item.expires_at,
                original_key=item.key,
            ),
        )
        if not _shortened(item):
            return JanitorActionDone(event=record)
        events.write(connection=connection, records=(record,))
        return JanitorActionDone()

    archived: tuple[tuple[JanitorArchiveCandidate, JanitorActionDone], ...] = run_janitor_phase(
        progress=progress,
        phase=JanitorPhase.ARCHIVE,
        items=plan.archive_candidates,
        describe=lambda candidate: JanitorProgressItem(
            action=JanitorAction.ARCHIVED,
            name=candidate.key.display_name(),
            destination=candidate.archive_key.display_name(),
        ),
        apply=archive_relation,
        workers=workers,
        chunks=_event_chunks(tuple(candidate.archive_key for candidate in plan.archive_candidates)),
        after_chunk=lambda finished: events.write(
            connection=workers.connection, records=_chunk_events(finished)
        ),
    )

    def delete_archive(*, item: JanitorArchivedRelation, connection: Any) -> JanitorActionDone:
        with OperationLifecycle(operation_kind="janitor", operation_name="janitor_cleanup_action"):
            _drop_archive(adapter=adapter, connection=connection, archive=item, recorder=recorder)
        return JanitorActionDone(
            event=_event_record(
                adapter=adapter,
                event_type=JanitorEventType.DELETE,
                run_id=run_id,
                archive=item,
            )
        )

    deleted: tuple[tuple[JanitorArchivedRelation, JanitorActionDone], ...] = run_janitor_phase(
        progress=progress,
        phase=JanitorPhase.DELETE_ARCHIVES,
        items=plan.archive_deletion_candidates,
        describe=lambda archive: JanitorProgressItem(
            action=JanitorAction.DELETED, name=archive.key.display_name()
        ),
        apply=delete_archive,
        workers=workers,
        chunks=_event_chunks(tuple(archive.key for archive in plan.archive_deletion_candidates)),
        after_chunk=lambda finished: events.write(
            connection=workers.connection, records=_chunk_events(finished)
        ),
    )
    return (
        tuple(candidate for candidate, _ in archived),
        tuple(archive for archive, _ in deleted),
    )


def _chunk_events(finished: tuple[JanitorActionDone, ...]) -> tuple[JanitorEventRecord, ...]:
    return tuple(done.event for done in finished if done.event is not None)


def _shortened(candidate: JanitorArchiveCandidate) -> bool:
    """Whether the archive name no longer ends with the relation's full original name."""

    return not candidate.archive_key.name.lower().endswith(
        ARCHIVE_NAME_SEPARATOR + candidate.key.name.lower()
    )


def _event_chunks(keys: tuple[JanitorRelationKey, ...]) -> tuple[tuple[int, ...], ...]:
    """Item positions grouped by schema, in order, and split into event-sized chunks."""

    by_schema: dict[tuple[str | None, str | None], list[int]] = {}
    index: int
    key: JanitorRelationKey
    for index, key in enumerate(keys):
        by_schema.setdefault((key.database, key.schema), []).append(index)
    chunks: list[tuple[int, ...]] = []
    positions: list[int]
    for positions in by_schema.values():
        start: int
        for start in range(0, len(positions), JANITOR_EVENT_CHUNK_SIZE):
            chunks.append(tuple(positions[start : start + JANITOR_EVENT_CHUNK_SIZE]))
    return tuple(chunks)


def _required_schema(key: JanitorRelationKey) -> str:
    if key.schema is None:
        raise ExecutorInputError(f"janitor archive action requires a schema: {key.display_name()}")
    return key.schema


def _is_view(relation_type: str | None) -> bool:
    return relation_type is not None and normalize_relation_type(relation_type) == RelationType.VIEW


def _qualified(*, adapter: BaseAdapter, key: JanitorRelationKey) -> str:
    return resolve_qualified_name_parts(
        adapter=adapter, database=key.database, schema=key.schema, name=key.name
    )


def _rename_relation(
    *,
    adapter: BaseAdapter,
    connection: Any,
    candidate: JanitorArchiveCandidate,
    recorder: StatementRecorder,
) -> None:
    origin: str = _qualified(adapter=adapter, key=candidate.key)
    destination: str = _qualified(adapter=adapter, key=candidate.archive_key)
    if not _is_view(candidate.relation.relation_type):
        adapter.rename(
            connection=connection,
            origin=origin,
            destination=destination,
            statement_recorder=recorder,
        )
        return
    statements: tuple[str, ...] = adapter.render_rename_view(origin=origin, destination=destination)
    recorder.record_many(statements)
    statement: str
    for statement in statements:
        _ = adapter.execute(connection=connection, sql=statement)


def _drop_archive(
    *,
    adapter: BaseAdapter,
    connection: Any,
    archive: JanitorArchivedRelation,
    recorder: StatementRecorder,
) -> None:
    destination: str = _qualified(adapter=adapter, key=archive.key)
    if _is_view(archive.relation_type):
        adapter.drop_view(
            connection=connection,
            destination=destination,
            if_exists=True,
            statement_recorder=recorder,
        )
        return
    adapter.drop(
        connection=connection,
        destination=destination,
        if_exists=True,
        statement_recorder=recorder,
    )


def _create_event_tables(
    *, adapter: BaseAdapter, connection: Any, plan: JanitorPlan
) -> tuple[tuple[str | None, str], ...]:
    keys: tuple[JanitorRelationKey, ...] = (
        *(candidate.key for candidate in plan.archive_candidates),
        *(archive.key for archive in plan.archive_deletion_candidates),
    )
    schemas: dict[tuple[str | None, str], None] = dict.fromkeys(
        (key.database, _required_schema(key)) for key in keys
    )
    database: str | None
    schema: str
    for database, schema in schemas:
        _ = adapter.execute(
            connection=connection,
            sql=adapter.render_create_janitor_event_table_sql(database=database, schema=schema),
        )
    return tuple(schemas)


def _event_record(
    *,
    adapter: BaseAdapter,
    event_type: JanitorEventType,
    run_id: str,
    archive: JanitorArchivedRelation,
) -> JanitorEventRecord:
    schema: str = _required_schema(archive.key)
    original: JanitorRelationKey | None = archive.original_key
    return JanitorEventRecord(
        event_id=build_janitor_event_id(
            event_type=event_type,
            run_id=run_id,
            relation_database=archive.key.database,
            relation_schema=schema,
            archive_name=archive.key.name,
        ),
        schema_version=JANITOR_EVENT_SCHEMA_VERSION,
        event_type=event_type,
        occurred_at=datetime.now(UTC),
        run_id=run_id,
        relation_database=archive.key.database,
        relation_schema=schema,
        relation_type=archive.relation_type,
        original_name=None if original is None else original.name,
        original_qualified_name=(
            None if original is None else _qualified(adapter=adapter, key=original)
        ),
        archive_name=archive.key.name,
        archive_qualified_name=_qualified(adapter=adapter, key=archive.key),
        archived_at=archive.archived_at,
    )
