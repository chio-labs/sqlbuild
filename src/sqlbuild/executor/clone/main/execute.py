"""Clone execution."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import RelationLookup
from sqlbuild.adapter.relations.main.relation_lookup import build_relation_lookup
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.planner.models import (
    CloneSourcePlanEntry,
    FunctionPlanEntry,
    ModelPlanEntry,
    SeedPlanEntry,
)
from sqlbuild.executor.clone._helpers.execution_items import (
    execute_clone_function_item,
    execute_clone_relation_item,
)
from sqlbuild.executor.clone._helpers.lifecycle import finish_clone, prepare_clone_destination
from sqlbuild.executor.clone.models import (
    CloneExecutionInput,
    CloneExecutionResult,
    CloneItemResult,
)
from sqlbuild.executor.clone.types import CloneStatus


def execute_clone(*, inputs: CloneExecutionInput) -> CloneExecutionResult:
    origin_models_by_name: dict[str, ModelPlanEntry] = {
        entry.name: entry for entry in inputs.origin_model_entries
    }
    origin_seeds_by_name: dict[str, SeedPlanEntry] = {
        entry.name: entry for entry in inputs.origin_seed_entries
    }
    origin_sources_by_name: dict[str, CloneSourcePlanEntry] = {
        entry.name: entry for entry in inputs.source_entries.origin
    }
    results: list[CloneItemResult] = []
    destination_entries: tuple[
        CloneSourcePlanEntry | SeedPlanEntry | ModelPlanEntry | FunctionPlanEntry, ...
    ] = (
        *inputs.source_entries.destination,
        *inputs.destination_seed_entries,
        *inputs.destination_model_entries,
        *inputs.destination_function_entries,
    )
    _ = prepare_clone_destination(
        inputs=inputs,
        destination_entries=destination_entries,
    )

    destination_entries_by_key: dict[
        CompiledObjectKey, CloneSourcePlanEntry | SeedPlanEntry | ModelPlanEntry | FunctionPlanEntry
    ] = {entry.key: entry for entry in destination_entries}
    ordered_destination_entries: tuple[
        CloneSourcePlanEntry | SeedPlanEntry | ModelPlanEntry | FunctionPlanEntry, ...
    ] = tuple(
        destination_entries_by_key[key]
        for key in inputs.execution_order
        if key in destination_entries_by_key
    )
    clonable_entries: tuple[
        tuple[
            CloneSourcePlanEntry | SeedPlanEntry | ModelPlanEntry,
            CloneSourcePlanEntry | SeedPlanEntry | ModelPlanEntry,
        ],
        ...,
    ] = tuple(
        (destination_entry, origin_entry)
        for destination_entry in ordered_destination_entries
        if not isinstance(destination_entry, FunctionPlanEntry)
        and (
            origin_entry := (
                origin_sources_by_name.get(destination_entry.name)
                or origin_seeds_by_name.get(destination_entry.name)
                or origin_models_by_name.get(destination_entry.name)
            )
        )
        is not None
    )
    relation_lookup: RelationLookup = build_relation_lookup(
        adapter=inputs.adapter,
        connection=inputs.destination_connection,
        locations=tuple(
            (
                origin_entry.destination.database,
                origin_entry.destination.schema,
                origin_entry.destination.name,
            )
            for _, origin_entry in clonable_entries
        )
        + tuple(
            (location.database, location.schema, location.name)
            for location in inputs.dependency_locations.values()
        ),
    )
    available_keys: set[CompiledObjectKey] = {
        key
        for key, location in inputs.dependency_locations.items()
        if relation_lookup.exists(
            database=location.database,
            schema=location.schema,
            name=location.name,
        )
    }
    origins_by_key: dict[
        CompiledObjectKey, CloneSourcePlanEntry | SeedPlanEntry | ModelPlanEntry
    ] = {destination.key: origin for destination, origin in clonable_entries}
    total: int = len(ordered_destination_entries)
    for index, destination_entry in enumerate(ordered_destination_entries, start=1):
        if isinstance(destination_entry, FunctionPlanEntry):
            item_result: CloneItemResult = execute_clone_function_item(
                destination_entry=destination_entry,
                inputs=inputs,
                available_keys=available_keys,
            )
            results.append(item_result)
            if inputs.on_item is not None:
                inputs.on_item(index=index, total=total, item=item_result)
            if item_result.status == CloneStatus.SUCCESS:
                available_keys.add(destination_entry.key)
            else:
                available_keys.discard(destination_entry.key)
            continue
        origin_entry: CloneSourcePlanEntry | SeedPlanEntry | ModelPlanEntry = origins_by_key[
            destination_entry.key
        ]
        item_result = execute_clone_relation_item(
            destination_entry=destination_entry,
            origin_entry=origin_entry,
            inputs=inputs,
            relation_lookup=relation_lookup,
            available_keys=available_keys,
        )
        results.append(item_result)
        if item_result.status == CloneStatus.SUCCESS:
            available_keys.add(destination_entry.key)
        elif item_result.status == CloneStatus.FAILED:
            available_keys.discard(destination_entry.key)
        if inputs.on_item is not None:
            inputs.on_item(index=index, total=total, item=item_result)

    return finish_clone(results=results, inputs=inputs)
