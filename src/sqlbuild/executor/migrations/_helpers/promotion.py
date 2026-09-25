"""Promote a verified migration stage and record the completed migration."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.compiler.migrations.constants import MIGRATION_WRITE_ATTEMPTS
from sqlbuild.compiler.migrations.main.deterministic_event_id import (
    deterministic_migration_event_id,
)
from sqlbuild.compiler.migrations.main.relation_for_location import migration_relation_for_location
from sqlbuild.compiler.migrations.main.write_event import write_migration_event
from sqlbuild.compiler.migrations.models import MigrationEvent, MigrationRelation
from sqlbuild.compiler.migrations.types import MigrationDecision
from sqlbuild.compiler.planner.models import ModelMigrationPlanEntry
from sqlbuild.executor.migrations.models import MigrationArtifactNames
from sqlbuild.executor.run.main.promote_staged_relation import promote_staged_relation


def promote_and_record(
    *,
    adapter: BaseAdapter,
    connection: Any,
    entry: ModelMigrationPlanEntry,
    names: MigrationArtifactNames,
    event: MigrationEvent,
) -> None:
    """Promote the stage, keeping a displaced destination, then append the migration event."""

    if not adapter.supports_transactional_ddl():
        _promote(adapter=adapter, connection=connection, names=names)
        record_event(adapter=adapter, connection=connection, event=event)
        return
    _ = adapter.execute(
        connection=connection,
        sql=adapter.render_create_migration_state_table_sql(
            database=event.destination.database, schema=event.destination.schema or ""
        ),
    )
    with adapter.transaction(connection):
        rebinds: tuple[str, ...] = (
            adapter.capture_dependent_view_rebinds(
                connection=connection,
                database=entry.destination.database,
                schema=entry.destination.schema or "",
                name=entry.destination.name,
            )
            if names.destination_exists
            else ()
        )
        _promote(adapter=adapter, connection=connection, names=names)
        statement: str
        for statement in rebinds:
            _ = adapter.execute(connection=connection, sql=statement)
        record_event(
            adapter=adapter, connection=connection, event=event, create_table=False, attempts=1
        )


def record_event(
    *,
    adapter: BaseAdapter,
    connection: Any,
    event: MigrationEvent,
    create_table: bool = True,
    attempts: int = MIGRATION_WRITE_ATTEMPTS,
) -> None:
    """Append one migration event through the adapter's state-table rendering."""

    write_migration_event(
        connection=connection,
        execute=adapter.execute,
        event=event,
        render_qualified_name=adapter.render_qualified_name,
        create_table_sql=(
            adapter.render_create_migration_state_table_sql(
                database=event.destination.database, schema=event.destination.schema or ""
            )
            if create_table
            else None
        ),
        attempts=attempts,
    )


def _promote(*, adapter: BaseAdapter, connection: Any, names: MigrationArtifactNames) -> None:
    promote_staged_relation(
        adapter=adapter,
        connection=connection,
        target_qualified=names.destination_qualified,
        staged_qualified=names.stage_qualified,
        displaced_qualified=names.displaced_qualified,
        target_exists=names.destination_exists,
        statement_recorder=StatementRecorder(),
    )


def migration_event(*, entry: ModelMigrationPlanEntry, run_id: str) -> MigrationEvent:
    """Build the append-only event recording one completed migration."""

    origin: MigrationRelation = migration_relation_for_location(entry.origin)
    destination: MigrationRelation = migration_relation_for_location(entry.destination)
    return MigrationEvent(
        event_id=deterministic_migration_event_id(
            run_id=run_id,
            target_name=entry.target_name,
            origin=origin,
            destination=destination,
        ),
        target_name=entry.target_name,
        origin_model=entry.origin_model,
        origin=origin,
        destination_model=entry.model_name,
        destination=destination,
        origin_version_hash=entry.origin_version_hash,
        discovery=entry.discovery,
        decision=entry.decision,
        run_id=run_id,
        created_at=datetime.now(tz=UTC),
    )


def record_renames(
    *,
    adapter: BaseAdapter,
    connection: Any,
    entries: tuple[ModelMigrationPlanEntry, ...],
    run_id: str,
) -> None:
    """Record each newly handed-over table or view rename so retries keep the identity."""

    entry: ModelMigrationPlanEntry
    for entry in entries:
        if entry.decision != MigrationDecision.RENAMED or entry.completed_at is not None:
            continue
        adapter.ensure_schema(
            connection=connection,
            database=entry.destination.database,
            schema=entry.destination.schema,
            statement_recorder=StatementRecorder(),
        )
        record_event(
            adapter=adapter,
            connection=connection,
            event=migration_event(entry=entry, run_id=run_id),
        )
