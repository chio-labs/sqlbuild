"""Execute planned direct-mode model migrations before any build node runs."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.types import MigrationTransfer
from sqlbuild.compiler.planner.models import ModelMigrationPlanEntry, PlanOutput
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.migrations._helpers.naming import resolve_artifact_names
from sqlbuild.executor.migrations._helpers.promotion import (
    migration_event,
    promote_and_record,
    record_renames,
)
from sqlbuild.executor.migrations._helpers.staging import create_stage, verify_stage
from sqlbuild.executor.migrations.models import MigrationArtifactNames


def apply_model_migrations(
    *,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection: Any,
    run_id: str,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """Stage, verify, and promote each pending migration, then record its event."""

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
        entry for entry in plan.migration_entries if entry.decision.moves_data
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
    _ = record_renames(
        adapter=adapter, connection=connection, entries=plan.migration_entries, run_id=run_id
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
        transfer: MigrationTransfer = _stage_promote_and_record(
            entry=entry, adapter=adapter, connection=connection, run_id=run_id
        )
    except Exception as error:
        raise ExecutorInputError(
            f"model migration {origin_label} -> {destination_label} failed: {error}",
            code="M106",
            help=(
                "Re-run the build; migration decisions are re-evaluated from recorded events. "
                "Any abandoned _sqb_archive__ stage is left for janitor to expire."
            ),
        ) from error
    if on_progress is not None:
        on_progress(
            f"Migrated {origin_label} -> {destination_label} by {transfer.label}"
            f"{' (clone refused)' if transfer != entry.transfer else ''}. "
            f"({time.monotonic() - started:.2f}s)"
        )


def _stage_promote_and_record(
    *, entry: ModelMigrationPlanEntry, adapter: BaseAdapter, connection: Any, run_id: str
) -> MigrationTransfer:
    adapter.ensure_schema(
        connection=connection,
        database=entry.destination.database,
        schema=entry.destination.schema,
        statement_recorder=StatementRecorder(),
    )
    names: MigrationArtifactNames = resolve_artifact_names(
        adapter=adapter, connection=connection, entry=entry, now=datetime.now(tz=UTC)
    )
    transfer: MigrationTransfer = create_stage(
        adapter=adapter, connection=connection, entry=entry, names=names
    )
    _ = verify_stage(
        adapter=adapter, connection=connection, entry=entry, names=names, transfer=transfer
    )
    _ = promote_and_record(
        adapter=adapter,
        connection=connection,
        entry=entry,
        names=names,
        event=migration_event(entry=entry, run_id=run_id),
    )
    return transfer
