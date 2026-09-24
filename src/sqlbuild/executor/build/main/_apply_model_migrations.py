"""Execute planned direct-mode model migrations before any build node runs."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.migrations.main.deterministic_event_id import (
    deterministic_migration_event_id,
)
from sqlbuild.compiler.migrations.main.write_event import write_migration_event
from sqlbuild.compiler.migrations.models import MigrationEvent, MigrationRelation
from sqlbuild.compiler.planner.models import ModelMigrationPlanEntry, PlanOutput
from sqlbuild.errors.contracts.exceptions import ExecutorInputError


def apply_model_migrations(
    *,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection: Any,
    run_id: str,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """Clone each pending migration origin over its destination, then record the event."""

    blocked: tuple[ModelMigrationPlanEntry, ...] = tuple(
        entry for entry in plan.migration_entries if entry.blocks_build
    )
    if blocked:
        raise ExecutorInputError(
            "model migrations are blocked for "
            + ", ".join(f"'{entry.model_name}' ({entry.decision.value})" for entry in blocked),
            code="M103",
        )
    pending: tuple[ModelMigrationPlanEntry, ...] = tuple(
        entry
        for entry in plan.migration_entries
        if entry.decision.moves_data and entry.statement is not None
    )
    entry: ModelMigrationPlanEntry
    for entry in pending:
        _ = _apply_one(
            entry=entry,
            adapter=adapter,
            connection=connection,
            run_id=run_id,
            on_progress=on_progress,
        )


def _apply_one(
    *,
    entry: ModelMigrationPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    run_id: str,
    on_progress: Callable[[str], None] | None,
) -> None:
    origin_label: str = entry.origin.qualified_name or entry.origin.name
    destination_label: str = entry.destination.qualified_name or entry.destination.name
    if on_progress is not None:
        on_progress(f"Migrating {origin_label} -> {destination_label} ({entry.decision.value})...")
    started: float = time.monotonic()
    try:
        _ = _clone_and_record(entry=entry, adapter=adapter, connection=connection, run_id=run_id)
    except Exception as error:
        raise ExecutorInputError(
            f"model migration {origin_label} -> {destination_label} failed: {error}",
            code="M106",
            help="Re-run the build; migration decisions are re-evaluated from recorded events.",
        ) from error
    if on_progress is not None:
        on_progress(
            f"Migrated {origin_label} -> {destination_label}. ({time.monotonic() - started:.2f}s)"
        )


def _clone_and_record(
    *, entry: ModelMigrationPlanEntry, adapter: BaseAdapter, connection: Any, run_id: str
) -> None:
    adapter.ensure_schema(
        connection=connection,
        database=entry.destination.database,
        schema=entry.destination.schema,
        statement_recorder=StatementRecorder(),
    )
    _ = adapter.execute(connection=connection, sql=entry.statement or "")
    origin: MigrationRelation = _relation(entry.origin)
    destination: MigrationRelation = _relation(entry.destination)
    write_migration_event(
        connection=connection,
        execute=adapter.execute,
        event=MigrationEvent(
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
        ),
        render_qualified_name=adapter.render_qualified_name,
        render_framework_type=adapter.render_framework_type,
        transient=adapter.state_tables_transient,
    )


def _relation(location: CompiledRelationLocation) -> MigrationRelation:
    return MigrationRelation(database=location.database, schema=location.schema, name=location.name)
