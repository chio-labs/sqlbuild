"""Clone execution."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.planner.models import ModelPlanEntry, SeedPlanEntry
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.executor.clone.helpers.operations import clone_relation, recreate_view
from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult


def _ensure_destination_schemas(
    *,
    destination_entries: tuple[SeedPlanEntry | ModelPlanEntry, ...],
    adapter: BaseAdapter,
    destination_connection: Any,
) -> None:
    schemas: set[tuple[str | None, str]] = set()
    entry: SeedPlanEntry | ModelPlanEntry
    for entry in destination_entries:
        if entry.destination.schema is not None:
            schemas.add((entry.destination.database, entry.destination.schema))
    recorder: StatementRecorder = StatementRecorder()
    for database, schema in sorted(schemas, key=lambda item: (item[0] or "", item[1])):
        adapter.ensure_schema(
            destination_connection,
            database=database,
            schema=schema,
            statement_recorder=recorder,
        )


def execute_clone(
    *,
    origin_model_entries: tuple[ModelPlanEntry, ...],
    destination_model_entries: tuple[ModelPlanEntry, ...],
    origin_seed_entries: tuple[SeedPlanEntry, ...],
    destination_seed_entries: tuple[SeedPlanEntry, ...],
    adapter: BaseAdapter,
    origin_connection: Any,
    destination_connection: Any,
    hard_copy: bool,
) -> CloneExecutionResult:
    origin_models_by_name: dict[str, ModelPlanEntry] = {
        entry.name: entry for entry in origin_model_entries
    }
    origin_seeds_by_name: dict[str, SeedPlanEntry] = {
        entry.name: entry for entry in origin_seed_entries
    }
    results: list[CloneItemResult] = []
    destination_entries: tuple[SeedPlanEntry | ModelPlanEntry, ...] = (
        *destination_seed_entries,
        *destination_model_entries,
    )
    _ensure_destination_schemas(
        destination_entries=destination_entries,
        adapter=adapter,
        destination_connection=destination_connection,
    )

    destination_entry: SeedPlanEntry | ModelPlanEntry
    for destination_entry in destination_entries:
        origin_entry: SeedPlanEntry | ModelPlanEntry | None = origin_seeds_by_name.get(
            destination_entry.name
        )
        if origin_entry is None:
            origin_entry = origin_models_by_name.get(destination_entry.name)
        if origin_entry is None:
            continue
        if (
            isinstance(destination_entry, ModelPlanEntry)
            and destination_entry.materialization_type == MaterializationType.VIEW
        ):
            results.append(
                recreate_view(
                    destination_entry=destination_entry,
                    origin_entry=origin_entry,
                    adapter=adapter,
                    origin_connection=origin_connection,
                    destination_connection=destination_connection,
                )
            )
            continue
        results.append(
            clone_relation(
                destination_entry=destination_entry,
                origin_entry=origin_entry,
                adapter=adapter,
                origin_connection=origin_connection,
                destination_connection=destination_connection,
                hard_copy=hard_copy,
            )
        )

    return CloneExecutionResult(item_results=tuple(results))
