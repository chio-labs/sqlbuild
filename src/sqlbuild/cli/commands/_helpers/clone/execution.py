"""Clone command execution phases."""

from __future__ import annotations

import time
from typing import TextIO

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands._helpers.clone.output import render_clone_item_line
from sqlbuild.cli.commands.models import (
    CloneCommandRequest,
    CloneConnectionContext,
    CloneExecutionPreparation,
    CloneInvocation,
    CloneRunOutcome,
)
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationLocation
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import (
    CloneSourcePlanEntry,
    FunctionPlanEntry,
    ModelPlanEntry,
    SeedPlanEntry,
)
from sqlbuild.executor.clone.main.execute import execute_clone
from sqlbuild.executor.clone.main.fingerprinting import copy_clone_fingerprints
from sqlbuild.executor.clone.models import (
    CloneExecutionInput,
    CloneExecutionResult,
    CloneItemResult,
    CloneSourceEntries,
)
from sqlbuild.executor.clone.types import CloneItemCallback
from sqlbuild.spec.contracts.models import SourceEntry


def execute_clone_plan(
    *,
    request: CloneCommandRequest,
    invocation: CloneInvocation,
    connection_context: CloneConnectionContext,
    preparation: CloneExecutionPreparation,
) -> CloneRunOutcome:
    """Execute the direct clone plan and copy fingerprints."""

    clone_start: float = time.monotonic()
    on_item: CloneItemCallback = _build_on_clone_item(
        stream=invocation.progress_stream,
        use_color=invocation.use_color,
    )
    result: CloneExecutionResult = execute_clone(
        inputs=CloneExecutionInput(
            source_entries=CloneSourceEntries(
                origin=preparation.pipeline_result.origin_source_entries,
                destination=preparation.pipeline_result.destination_source_entries,
            ),
            origin_model_entries=preparation.pipeline_result.origin_model_entries,
            destination_model_entries=preparation.pipeline_result.destination_model_entries,
            origin_seed_entries=preparation.pipeline_result.origin_seed_entries,
            destination_seed_entries=preparation.pipeline_result.destination_seed_entries,
            destination_function_entries=preparation.pipeline_result.destination_function_entries,
            execution_order=preparation.pipeline_result.clone_plan.execution_order,
            adapter=invocation.adapter,
            destination_connection=connection_context.destination_connection,
            hard_copy=request.hard_copy,
            run_id=preparation.pipeline_result.destination_project.run_id,
            query_change_tracking=preparation.pipeline_result.destination_project.settings.query_change_tracking,
            upstream_deps=preparation.pipeline_result.clone_plan.upstream_deps,
            dependency_locations=_clone_dependency_locations(
                preparation=preparation,
                adapter=invocation.adapter,
            ),
            on_item=on_item,
        )
    )
    copy_clone_fingerprints(
        result=result,
        origin_model_entries=preparation.pipeline_result.origin_model_entries,
        destination_model_entries=preparation.pipeline_result.destination_model_entries,
        origin_seed_entries=preparation.pipeline_result.origin_seed_entries,
        destination_seed_entries=preparation.pipeline_result.destination_seed_entries,
        adapter=invocation.adapter,
        destination_connection=connection_context.destination_connection,
        run_id=preparation.pipeline_result.destination_project.run_id,
        query_change_tracking=preparation.pipeline_result.destination_project.settings.query_change_tracking,
    )
    return CloneRunOutcome(result=result, elapsed=time.monotonic() - clone_start)


def _clone_dependency_locations(
    *, preparation: CloneExecutionPreparation, adapter: BaseAdapter
) -> dict[CompiledObjectKey, CompiledRelationLocation]:
    entries: tuple[
        CloneSourcePlanEntry | ModelPlanEntry | SeedPlanEntry | FunctionPlanEntry, ...
    ] = (
        *preparation.pipeline_result.destination_source_entries,
        *preparation.pipeline_result.destination_model_entries,
        *preparation.pipeline_result.destination_seed_entries,
        *preparation.pipeline_result.destination_function_entries,
    )
    locations: dict[CompiledObjectKey, CompiledRelationLocation] = {
        entry.key: entry.destination for entry in entries
    }
    source_map: dict[str, SourceEntry] = (
        preparation.pipeline_result.clone_plan.source_read_map
        or preparation.pipeline_result.clone_plan.source_map
    )
    for name, source in source_map.items():
        if source.table is None:
            continue
        key: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.SOURCE, name)
        locations[key] = CompiledRelationLocation(
            database=source.database,
            schema=source.schema,
            name=source.table,
            qualified_name=(
                adapter.render_qualified_name(
                    database=source.database,
                    schema=source.schema,
                    name=source.table,
                )
                or source.table
            ),
        )
    return locations


def _build_on_clone_item(*, stream: TextIO, use_color: bool) -> CloneItemCallback:
    def _on_clone_item(*, index: int, total: int, item: CloneItemResult) -> None:
        stream.write(
            render_clone_item_line(index=index, total=total, item=item, use_color=use_color) + "\n"
        )
        stream.flush()

    return _on_clone_item
