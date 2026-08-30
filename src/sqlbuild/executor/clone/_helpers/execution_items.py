"""Per-item clone execution decisions."""

from __future__ import annotations

import time

from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import RelationLookup
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
from sqlbuild.executor.clone.models import CloneExecutionInput, CloneItemResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from sqlbuild.executor.functions.main._execute import execute_function
from sqlbuild.executor.scheduling.types import ExecutionStatus


def execute_clone_function_item(
    *,
    destination_entry: FunctionPlanEntry,
    inputs: CloneExecutionInput,
    available_keys: set[CompiledObjectKey],
) -> CloneItemResult:
    """Recreate one function and normalize its clone outcome."""

    missing_dependencies: tuple[CompiledObjectKey, ...] = _missing_destination_dependencies(
        key=destination_entry.key,
        inputs=inputs,
        available_keys=available_keys,
    )
    if missing_dependencies:
        return _missing_dependency_result(
            name=destination_entry.name,
            destination_relation=destination_entry.destination.qualified_name,
            missing_dependencies=missing_dependencies,
            inputs=inputs,
        )
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
    return CloneItemResult(
        name=destination_entry.name,
        action=CloneAction.RECREATED_FUNCTION if succeeded else CloneAction.FAILED,
        status=CloneStatus.SUCCESS if succeeded else CloneStatus.FAILED,
        message=(
            "; ".join(function_result.warning_messages)
            if succeeded and function_result.warning_messages
            else function_result.error_message
        ),
        destination_relation=destination_entry.destination.qualified_name,
        duration_seconds=time.monotonic() - start,
        executed_statements=function_result.lifecycle_events,
    )


def execute_clone_relation_item(
    *,
    destination_entry: CloneSourcePlanEntry | SeedPlanEntry | ModelPlanEntry,
    origin_entry: CloneSourcePlanEntry | SeedPlanEntry | ModelPlanEntry,
    inputs: CloneExecutionInput,
    relation_lookup: RelationLookup,
    available_keys: set[CompiledObjectKey],
) -> CloneItemResult:
    """Clone a physical relation or conditionally recreate one view."""

    if (
        not isinstance(destination_entry, ModelPlanEntry)
        or not isinstance(origin_entry, ModelPlanEntry)
        or destination_entry.materialization_type != MaterializationType.VIEW
    ):
        return clone_relation(
            destination_entry=destination_entry,
            origin_entry=origin_entry,
            adapter=inputs.adapter,
            destination_connection=inputs.destination_connection,
            hard_copy=inputs.hard_copy,
            origin_lookup=relation_lookup,
        )
    missing_dependencies: tuple[CompiledObjectKey, ...] = _missing_destination_dependencies(
        key=destination_entry.key,
        inputs=inputs,
        available_keys=available_keys,
    )
    if missing_dependencies:
        return _missing_dependency_result(
            name=destination_entry.name,
            origin_relation=origin_entry.destination.qualified_name,
            destination_relation=destination_entry.destination.qualified_name,
            missing_dependencies=missing_dependencies,
            inputs=inputs,
        )
    return recreate_view(
        destination_entry=destination_entry,
        origin_entry=origin_entry,
        adapter=inputs.adapter,
        destination_connection=inputs.destination_connection,
    )


def _missing_destination_dependencies(
    *,
    key: CompiledObjectKey,
    inputs: CloneExecutionInput,
    available_keys: set[CompiledObjectKey],
) -> tuple[CompiledObjectKey, ...]:
    return tuple(
        dependency
        for dependency in inputs.upstream_deps.get(key, ())
        if dependency in inputs.dependency_locations and dependency not in available_keys
    )


def _missing_dependency_result(
    *,
    name: str,
    destination_relation: str | None,
    missing_dependencies: tuple[CompiledObjectKey, ...],
    inputs: CloneExecutionInput,
    origin_relation: str | None = None,
) -> CloneItemResult:
    return CloneItemResult(
        name=name,
        action=CloneAction.SKIPPED_MISSING_DEPENDENCY,
        status=CloneStatus.WARNING,
        message="missing destination dependencies: "
        + ", ".join(
            inputs.dependency_locations[dependency].qualified_name
            or inputs.dependency_locations[dependency].name
            for dependency in missing_dependencies
        ),
        origin_relation=origin_relation,
        destination_relation=destination_relation,
    )
