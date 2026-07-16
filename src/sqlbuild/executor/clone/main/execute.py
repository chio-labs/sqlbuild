"""Clone execution."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import RelationLookup
from sqlbuild.adapter.relations.main.relation_lookup import build_relation_lookup
from sqlbuild.compiler.planner.models import ModelPlanEntry, SeedPlanEntry
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.executor.clone._helpers.operations import clone_relation, recreate_view
from sqlbuild.executor.clone.models import CloneExecutionResult, CloneItemResult
from sqlbuild.executor.clone.types import CloneItemCallback


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
            connection=destination_connection,
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
    on_item: CloneItemCallback | None = None,
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
    _ = _ensure_destination_schemas(
        destination_entries=destination_entries,
        adapter=adapter,
        destination_connection=destination_connection,
    )

    clonable_entries: tuple[
        tuple[SeedPlanEntry | ModelPlanEntry, SeedPlanEntry | ModelPlanEntry], ...
    ] = tuple(
        (destination_entry, origin_entry)
        for destination_entry in destination_entries
        if (
            origin_entry := (
                origin_seeds_by_name.get(destination_entry.name)
                or origin_models_by_name.get(destination_entry.name)
            )
        )
        is not None
    )
    origin_lookup: RelationLookup = build_relation_lookup(
        adapter=adapter,
        connection=origin_connection,
        locations=tuple(
            (
                origin_entry.destination.database,
                origin_entry.destination.schema,
                origin_entry.destination.name,
            )
            for _, origin_entry in clonable_entries
        ),
    )
    total: int = len(clonable_entries)
    index: int = 0
    destination_entry: SeedPlanEntry | ModelPlanEntry
    origin_entry: SeedPlanEntry | ModelPlanEntry
    for destination_entry, origin_entry in clonable_entries:
        index += 1
        if (
            isinstance(destination_entry, ModelPlanEntry)
            and destination_entry.materialization_type == MaterializationType.VIEW
        ):
            item_result: CloneItemResult = recreate_view(
                destination_entry=destination_entry,
                origin_entry=origin_entry,
                adapter=adapter,
                destination_connection=destination_connection,
                origin_lookup=origin_lookup,
            )
        else:
            item_result = clone_relation(
                destination_entry=destination_entry,
                origin_entry=origin_entry,
                adapter=adapter,
                destination_connection=destination_connection,
                hard_copy=hard_copy,
                origin_lookup=origin_lookup,
            )
        results.append(item_result)
        if on_item is not None:
            on_item(index=index, total=total, item=item_result)

    return CloneExecutionResult(item_results=tuple(results))
