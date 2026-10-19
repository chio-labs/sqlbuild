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
from sqlbuild.executor.janitor.models import (
    JanitorArchiveCandidate,
    JanitorArchivedRelation,
    JanitorPlan,
    JanitorRelationKey,
)
from sqlbuild.executor.janitor_events.constants import JANITOR_EVENT_SCHEMA_VERSION
from sqlbuild.executor.janitor_events.main.janitor_event_id import build_janitor_event_id
from sqlbuild.executor.janitor_events.main.write_janitor_event import write_janitor_event_record
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
    connection: Any,
    recorder: StatementRecorder,
    run_id: str,
) -> tuple[tuple[JanitorArchiveCandidate, ...], tuple[JanitorArchivedRelation, ...]]:
    """Rename stale relations to archives, then drop expired archives by name."""

    _create_event_tables(adapter=adapter, connection=connection, plan=plan)
    archived: list[JanitorArchiveCandidate] = []
    candidate: JanitorArchiveCandidate
    for candidate in plan.archive_candidates:
        with OperationLifecycle(operation_kind="janitor", operation_name="janitor_cleanup_action"):
            _rename_relation(
                adapter=adapter,
                connection=connection,
                candidate=candidate,
                recorder=recorder,
            )
        archived.append(candidate)
        _write_event(
            adapter=adapter,
            connection=connection,
            record=_event_record(
                adapter=adapter,
                event_type=JanitorEventType.ARCHIVE,
                run_id=run_id,
                archive=JanitorArchivedRelation(
                    key=candidate.archive_key,
                    relation_type=candidate.relation.relation_type,
                    archived_at=candidate.archived_at,
                    expires_at=candidate.expires_at,
                    original_key=candidate.key,
                ),
            ),
        )
    deleted: list[JanitorArchivedRelation] = []
    archive: JanitorArchivedRelation
    for archive in plan.archive_deletion_candidates:
        with OperationLifecycle(operation_kind="janitor", operation_name="janitor_cleanup_action"):
            _drop_archive(
                adapter=adapter, connection=connection, archive=archive, recorder=recorder
            )
        deleted.append(archive)
        _write_event(
            adapter=adapter,
            connection=connection,
            record=_event_record(
                adapter=adapter,
                event_type=JanitorEventType.DELETE,
                run_id=run_id,
                archive=archive,
            ),
        )
    return tuple(archived), tuple(deleted)


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


def _create_event_tables(*, adapter: BaseAdapter, connection: Any, plan: JanitorPlan) -> None:
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


def _write_event(*, adapter: BaseAdapter, connection: Any, record: JanitorEventRecord) -> None:
    _ = write_janitor_event_record(
        connection=connection,
        execute=adapter.execute,
        record=record,
        render_qualified_name=adapter.render_qualified_name,
    )
