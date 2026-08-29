"""Clone execution."""

from __future__ import annotations

import time
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import RelationLookup
from sqlbuild.adapter.relations.main.relation_lookup import build_relation_lookup
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.planner.models import (
    CloneSourcePlanEntry,
    FunctionPlanEntry,
    ModelPlanEntry,
    SeedPlanEntry,
)
from sqlbuild.compiler.planner.types import MaterializationType
from sqlbuild.executor.build.models import FunctionExecutionResult
from sqlbuild.executor.clone._helpers.operations import clone_relation, recreate_view
from sqlbuild.executor.clone.models import (
    CloneExecutionInput,
    CloneExecutionResult,
    CloneItemResult,
)
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from sqlbuild.executor.functions.main._execute import execute_function
from sqlbuild.executor.scheduling.types import ExecutionStatus


def _ensure_destination_schemas(
    *,
    destination_entries: tuple[
        CloneSourcePlanEntry | SeedPlanEntry | ModelPlanEntry | FunctionPlanEntry, ...
    ],
    adapter: BaseAdapter,
    destination_connection: Any,
) -> None:
    schemas: set[tuple[str | None, str]] = set()
    entry: CloneSourcePlanEntry | SeedPlanEntry | ModelPlanEntry | FunctionPlanEntry
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
    _ = _ensure_destination_schemas(
        destination_entries=destination_entries,
        adapter=inputs.adapter,
        destination_connection=inputs.destination_connection,
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
    origin_lookup: RelationLookup = build_relation_lookup(
        adapter=inputs.adapter,
        connection=inputs.origin_connection,
        locations=tuple(
            (
                origin_entry.destination.database,
                origin_entry.destination.schema,
                origin_entry.destination.name,
            )
            for _, origin_entry in clonable_entries
        ),
    )
    origins_by_key: dict[
        CompiledObjectKey, CloneSourcePlanEntry | SeedPlanEntry | ModelPlanEntry
    ] = {destination.key: origin for destination, origin in clonable_entries}
    total: int = len(ordered_destination_entries)
    for index, destination_entry in enumerate(ordered_destination_entries, start=1):
        if isinstance(destination_entry, FunctionPlanEntry):
            start: float = time.monotonic()
            recorder: StatementRecorder = StatementRecorder()
            function_result: FunctionExecutionResult = execute_function(
                function_entry=destination_entry,
                adapter=inputs.adapter,
                connection=inputs.destination_connection,
                statement_recorder=recorder,
                run_id=inputs.run_id,
                query_change_tracking=inputs.query_change_tracking,
            )
            succeeded: bool = function_result.status == ExecutionStatus.SUCCESS
            item_result: CloneItemResult = CloneItemResult(
                name=destination_entry.name,
                action=(CloneAction.RECREATED_FUNCTION if succeeded else CloneAction.FAILED),
                status=(CloneStatus.SUCCESS if succeeded else CloneStatus.FAILED),
                message=(
                    "; ".join(function_result.warning_messages)
                    if succeeded and function_result.warning_messages
                    else function_result.error_message
                ),
                destination_relation=destination_entry.destination.qualified_name,
                duration_seconds=time.monotonic() - start,
                executed_statements=function_result.lifecycle_events,
            )
            results.append(item_result)
            if inputs.on_item is not None:
                inputs.on_item(index=index, total=total, item=item_result)
            continue
        origin_entry: CloneSourcePlanEntry | SeedPlanEntry | ModelPlanEntry = origins_by_key[
            destination_entry.key
        ]
        if (
            isinstance(destination_entry, ModelPlanEntry)
            and isinstance(origin_entry, ModelPlanEntry)
            and destination_entry.materialization_type == MaterializationType.VIEW
        ):
            item_result: CloneItemResult = recreate_view(
                destination_entry=destination_entry,
                origin_entry=origin_entry,
                adapter=inputs.adapter,
                destination_connection=inputs.destination_connection,
                origin_lookup=origin_lookup,
            )
        else:
            item_result = clone_relation(
                destination_entry=destination_entry,
                origin_entry=origin_entry,
                adapter=inputs.adapter,
                destination_connection=inputs.destination_connection,
                hard_copy=inputs.hard_copy,
                origin_lookup=origin_lookup,
            )
        results.append(item_result)
        if inputs.on_item is not None:
            inputs.on_item(index=index, total=total, item=item_result)

    return CloneExecutionResult(item_results=tuple(results))
