"""Public dependency baseline execution entrypoint."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.relations.main.resolve_relation_location_qualified_name import (
    resolve_relation_location_qualified_name,
)
from sqlbuild.compiler.planner.models import DependencyBaselinePlanEntry
from sqlbuild.executor.run._helpers.reuse.core import (
    create_relation_from_reuse_origin,
    create_relation_from_reuse_plan,
)
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.run.types import ExecutionPhase
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.runtime.contracts.types import ExecutionResourceKind, NodeStartCallback


def execute_dependency_baseline_entries(
    *,
    entries: tuple[DependencyBaselinePlanEntry, ...],
    adapter: BaseAdapter,
    connection: Any,
    on_node_start: NodeStartCallback | None = None,
    on_node_complete: Callable[[object], None] | None = None,
) -> tuple[ModelExecutionResult, ...]:
    """Copy/clone dependency baseline relations without writing model fingerprints."""

    results: list[ModelExecutionResult] = []
    entry: DependencyBaselinePlanEntry
    for entry in entries:
        if on_node_start is not None:
            on_node_start(name=entry.name, resource_kind=ExecutionResourceKind.TABLE)
        result: ModelExecutionResult = _execute_dependency_baseline_entry(
            entry=entry,
            adapter=adapter,
            connection=connection,
        )
        results.append(result)
        if on_node_complete is not None:
            on_node_complete(result)
        if result.status == ExecutionStatus.FAILED:
            break
    return tuple(results)


def _execute_dependency_baseline_entry(
    *, entry: DependencyBaselinePlanEntry, adapter: BaseAdapter, connection: Any
) -> ModelExecutionResult:
    warnings: list[str] = []
    statement_recorder: StatementRecorder = StatementRecorder()
    destination: str = resolve_relation_location_qualified_name(
        adapter=adapter,
        location=entry.destination,
    )
    if entry.relation_reuse is None:
        return _failed_dependency_baseline_result(
            entry=entry,
            error=f"dependency '{entry.name}' dependency baseline has no relation reuse plan",
            statement_recorder=statement_recorder,
        )
    try:
        adapter.ensure_schema(
            connection=connection,
            database=entry.destination.database,
            schema=entry.destination.schema,
            statement_recorder=statement_recorder,
        )
        adapter.drop(
            connection=connection,
            destination=destination,
            if_exists=True,
            statement_recorder=statement_recorder,
        )
        if entry.fingerprint_version_hash is None:
            _ = create_relation_from_reuse_origin(
                adapter=adapter,
                connection=connection,
                origin_relation=entry.relation_reuse.origin.qualified_name
                or entry.relation_reuse.origin.name,
                destination_relation=destination,
                hard_copy=entry.relation_reuse.hard_copy,
                statement_recorder=statement_recorder,
                destination_target_name=entry.relation_reuse.destination_target_name,
                reuse_from_target_name=entry.relation_reuse.reuse_from_target_name,
            )
        else:
            _ = create_relation_from_reuse_plan(
                adapter=adapter,
                connection=connection,
                model_name=entry.name,
                expected_version_hash=entry.fingerprint_version_hash,
                relation_reuse=entry.relation_reuse,
                destination_relation=destination,
                statement_recorder=statement_recorder,
            )
    except Exception as exc:
        return _failed_dependency_baseline_result(
            entry=entry,
            error=str(exc),
            statement_recorder=statement_recorder,
        )
    return ModelExecutionResult(
        model_name=entry.name,
        status=ExecutionStatus.SUCCESS,
        promoted_relation=destination,
        warning_messages=tuple(warnings),
        lifecycle_events=statement_recorder.snapshot(),
    )


def _failed_dependency_baseline_result(
    *, entry: DependencyBaselinePlanEntry, error: str, statement_recorder: StatementRecorder
) -> ModelExecutionResult:
    statement_recorder.log(f"dependency baseline {entry.name} failed error={error}")
    return ModelExecutionResult(
        model_name=entry.name,
        status=ExecutionStatus.FAILED,
        failed_phase=ExecutionPhase.STAGING,
        warning_messages=(),
        lifecycle_events=statement_recorder.snapshot(),
        error_message=error,
    )
