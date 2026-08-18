"""Concurrent build scheduler dispatch helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.adapter.contract.types import TablePromotionMode
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.compiler.planner.types import (
    IncrementalMode,
    MaterializationType,
    PlanAction,
    PlanReason,
)
from sqlbuild.executor.build.constants import (
    BUILD_CUSTOM_MATERIALIZATION_MISSING_CODE,
    BUILD_SOURCE_FRESHNESS_BLOCKED_CODE,
    BUILD_WORKER_FAILED_CODE,
    INCREMENTAL_ACTIONS,
)
from sqlbuild.executor.build.models import (
    FunctionExecutionResult,
    NodeCompletion,
    SeedExecutionResult,
)
from sqlbuild.executor.custom.models import MaterializationResult
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.run.main._execute import (
    execute_custom_entry,
    execute_incremental_entry,
    execute_microbatch_entry,
    execute_snapshot_entry,
    execute_table_entry,
    execute_view_entry,
)
from sqlbuild.executor.run.models import ModelExecutionResult, ModelMaterializationContext
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.runtime.contracts.types import ExecutionResourceKind
from sqlbuild.spec.contracts.models import SnapshotsConfig

type _BuildWorkerResult = (
    ModelExecutionResult
    | SeedExecutionResult
    | FunctionExecutionResult
    | SqlTestExecutionResult
    | LoadExecutionResult
)


def _build_worker_success_completion(
    *, key: CompiledObjectKey, result: _BuildWorkerResult
) -> NodeCompletion:
    return NodeCompletion(key=key, result=result)


def _build_worker_failure_completion(*, key: CompiledObjectKey, error: Exception) -> NodeCompletion:
    return NodeCompletion(
        key=key,
        result=ModelExecutionResult(
            model_name=key.name,
            status=ExecutionStatus.FAILED,
            error_code=BUILD_WORKER_FAILED_CODE,
            error_message=str(error),
        ),
    )


def _dispatch_model(
    *,
    context: ModelMaterializationContext,
    promotion_mode: TablePromotionMode,
    snapshots: SnapshotsConfig,
    allow_snapshot_schema_change: bool,
    custom_materializations: Mapping[str, Callable[..., MaterializationResult]] | None = None,
    target: str = "",
    effective_vars: dict[str, object] | None = None,
    warehouse_relations: dict[str, RelationInfo] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> ModelExecutionResult:
    """Route a model to the correct executor based on action and mode."""

    entry: ModelPlanEntry = context.entry
    if entry.action == PlanAction.SKIP:
        return ModelExecutionResult(
            model_name=entry.name,
            status=ExecutionStatus.SKIPPED,
            skip_reason=_plan_skip_reason(entry),
            error_code=_plan_skip_error_code(entry),
        )

    if entry.action == PlanAction.CUSTOM:
        mat_name: str | None = entry.custom_materialization_name
        registry: Mapping[str, Callable[..., MaterializationResult]] = custom_materializations or {}
        if mat_name is None or mat_name not in registry:
            return ModelExecutionResult(
                model_name=entry.name,
                status=ExecutionStatus.FAILED,
                error_code=BUILD_CUSTOM_MATERIALIZATION_MISSING_CODE,
                error_message=f"custom materialization '{mat_name}' not found in registry",
            )
        existing: RelationInfo | None = (warehouse_relations or {}).get(entry.name)
        return execute_custom_entry(
            context=context,
            declared_columns=entry.declared_columns,
            materialize_fn=registry[mat_name],
            target=target,
            effective_vars=effective_vars or {},
            existing_relation=existing,
            on_progress=on_progress,
        )

    is_microbatch: bool = entry.incremental_mode == IncrementalMode.MICROBATCH
    is_full_refresh_microbatch: bool = (
        is_microbatch
        and entry.action == PlanAction.CREATE_TABLE
        and entry.materialization_type == MaterializationType.INCREMENTAL
    )

    if is_microbatch and entry.action in INCREMENTAL_ACTIONS:
        return execute_microbatch_entry(
            context=context,
            declared_columns=entry.declared_columns,
            on_progress=on_progress,
        )
    if is_full_refresh_microbatch:
        return execute_microbatch_entry(
            context=context,
            declared_columns=entry.declared_columns,
            is_full_refresh=True,
            on_progress=on_progress,
        )
    if entry.action in INCREMENTAL_ACTIONS:
        return execute_incremental_entry(
            context=context,
            declared_columns=entry.declared_columns,
        )
    if entry.action == PlanAction.CREATE_VIEW:
        return execute_view_entry(context=context)
    if entry.action == PlanAction.SNAPSHOT:
        return execute_snapshot_entry(
            context=context,
            snapshots=snapshots,
            allow_snapshot_schema_change=allow_snapshot_schema_change,
        )
    return execute_table_entry(
        context=context,
        declared_columns=entry.declared_columns,
        promotion_mode=promotion_mode,
    )


def _plan_skip_reason(entry: ModelPlanEntry) -> str:
    if entry.reason == PlanReason.SOURCE_FRESHNESS_ERROR:
        return "Blocked by source freshness error"
    return entry.reason.value


def _plan_skip_error_code(entry: ModelPlanEntry) -> str | None:
    if entry.reason == PlanReason.SOURCE_FRESHNESS_ERROR:
        return BUILD_SOURCE_FRESHNESS_BLOCKED_CODE
    return None


def _model_execution_resource_kind(materialization_type: str) -> ExecutionResourceKind:
    if materialization_type == MaterializationType.VIEW:
        return ExecutionResourceKind.VIEW
    if materialization_type == MaterializationType.CUSTOM:
        return ExecutionResourceKind.CUSTOM
    if materialization_type == MaterializationType.SNAPSHOT:
        return ExecutionResourceKind.SNAPSHOT
    return ExecutionResourceKind.TABLE
