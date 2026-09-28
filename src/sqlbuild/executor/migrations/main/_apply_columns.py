"""Execute planned in-place column renames before any build node runs."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ColumnMigrationPlanEntry, PlanOutput
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.migrations._helpers.columns import apply_model_column_renames


def apply_column_migrations(
    *,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection: Any,
    run_id: str,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """Rename each model's pending columns and record them, one model at a time."""

    blocked: tuple[ColumnMigrationPlanEntry, ...] = tuple(
        entry for entry in plan.column_migration_entries if entry.blocks_build
    )
    if blocked:
        raise ExecutorInputError(
            "column migrations are blocked for "
            + ", ".join(f"'{entry.model_name}' ({entry.decision.value})" for entry in blocked),
            code="M110",
        )
    pending: tuple[ColumnMigrationPlanEntry, ...] = tuple(
        entry for entry in plan.column_migration_entries if entry.decision.records_event
    )
    model_name: str
    for model_name in dict.fromkeys(entry.model_name for entry in pending):
        _ = _apply_model(
            entries=tuple(entry for entry in pending if entry.model_name == model_name),
            adapter=adapter,
            connection=connection,
            run_id=run_id,
            on_progress=on_progress,
        )


def _apply_model(
    *,
    entries: tuple[ColumnMigrationPlanEntry, ...],
    adapter: BaseAdapter,
    connection: Any,
    run_id: str,
    on_progress: Callable[[str], None] | None,
) -> None:
    relation: str = entries[0].destination.qualified_name or entries[0].destination.name
    renames: str = ", ".join(
        f"{entry.origin_column} -> {entry.destination_column}" for entry in entries
    )
    if on_progress is not None:
        on_progress(f"Renaming columns of {relation} ({renames})...")
    started: float = time.monotonic()
    try:
        _ = apply_model_column_renames(
            adapter=adapter, connection=connection, entries=entries, run_id=run_id
        )
    except Exception as error:
        raise ExecutorInputError(
            f"column migration {renames} on {relation} failed: {error}",
            code="M113",
            help=(
                "Re-run the build; column renames are re-evaluated from the table's current "
                "columns and recorded events, so completed renames are not repeated."
            ),
        ) from error
    if on_progress is not None:
        on_progress(
            f"Renamed columns of {relation} ({renames}). ({time.monotonic() - started:.2f}s)"
        )
