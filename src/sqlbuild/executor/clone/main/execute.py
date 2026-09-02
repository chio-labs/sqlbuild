"""Clone execution."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import RelationLookup
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.planner.models import (
    CloneSourcePlanEntry,
    FunctionPlanEntry,
    ModelPlanEntry,
    SeedPlanEntry,
)
from sqlbuild.executor.clone._helpers.canonical_progress import clone_item_enrichment
from sqlbuild.executor.clone._helpers.execution_items import (
    execute_clone_destination_item,
)
from sqlbuild.executor.clone._helpers.inspection import build_clone_relation_lookup
from sqlbuild.executor.clone._helpers.lifecycle import finish_clone, prepare_clone_destination
from sqlbuild.executor.clone.models import (
    CloneExecutionInput,
    CloneExecutionResult,
    CloneItemResult,
)
from sqlbuild.executor.clone.types import CloneStatus
from sqlbuild.observability import run_scope
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle
from sqlbuild.runtime.observability.classes.resource_attempt_lifecycle import (
    ResourceAttemptLifecycle,
)


def execute_clone(*, inputs: CloneExecutionInput) -> CloneExecutionResult:
    with run_scope(inputs.run_id):
        with OperationLifecycle(
            operation_kind="clone",
            operation_name="clone_execution",
            metadata={"item_count": len(inputs.execution_order)},
        ) as lifecycle:
            result: CloneExecutionResult = _execute_clone(inputs=inputs)
            if any(item.status == CloneStatus.FAILED for item in result.item_results):
                lifecycle.failed(error_code="clone_execution_failed")
            return result


def _execute_clone(*, inputs: CloneExecutionInput) -> CloneExecutionResult:
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
    relation_lookup: RelationLookup = build_clone_relation_lookup(
        inputs=inputs, clonable_entries=clonable_entries
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
        resource_kind: str = str(destination_entry.key.resource_type)
        with clone_item_enrichment(
            resource_name=destination_entry.name, enabled=inputs.on_item is not None
        ):
            with ResourceAttemptLifecycle(
                resource_id=f"{resource_kind}:{destination_entry.name}",
                resource_kind=resource_kind,
                resource_name=destination_entry.name,
                run_id=inputs.run_id,
            ) as lifecycle:
                item_result: CloneItemResult = execute_clone_destination_item(
                    destination_entry=destination_entry,
                    inputs=inputs,
                    origins_by_key=origins_by_key,
                    relation_lookup=relation_lookup,
                    available_keys=available_keys,
                )
                if item_result.status == CloneStatus.FAILED:
                    lifecycle.failed(error_code="clone_item_failed")
        results.append(item_result)
        available_keys = _updated_available_keys(
            available_keys=available_keys,
            destination_entry=destination_entry,
            item_result=item_result,
        )
        if inputs.on_item is not None:
            inputs.on_item(index=index, total=total, item=item_result)

    return finish_clone(results=results, inputs=inputs)


def _updated_available_keys(
    *,
    available_keys: set[CompiledObjectKey],
    destination_entry: CloneSourcePlanEntry | SeedPlanEntry | ModelPlanEntry | FunctionPlanEntry,
    item_result: CloneItemResult,
) -> set[CompiledObjectKey]:
    if item_result.status == CloneStatus.SUCCESS:
        available_keys.add(destination_entry.key)
    elif item_result.status == CloneStatus.FAILED or isinstance(
        destination_entry, FunctionPlanEntry
    ):
        available_keys.discard(destination_entry.key)
    return available_keys
