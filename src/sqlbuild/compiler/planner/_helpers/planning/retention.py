"""Warehouse-aware retention planning."""

from __future__ import annotations

from collections import defaultdict

from sqlbuild.adapter.contract.models import (
    RenderedRetentionChange,
    RetentionRequest,
    RetentionState,
)
from sqlbuild.adapter.contract.types import BuiltinAdapter, RetentionChangePhase, RetentionScope
from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import (
    PlannerRuntime,
    PlannerScope,
    PlannerWarehouseState,
    RetentionPlanEntry,
)
from sqlbuild.compiler.planner.types import RetentionDirection, RetentionPlanPhase
from sqlbuild.spec.contracts.main.resolve_target_config import resolve_target_config
from sqlbuild.spec.contracts.models import ResolvedTimeTravelRetention, TargetConfig

_DECREASE_WARNING: str = "Retention decreases are irreversible once warehouse history expires."


def plan_retention(
    *,
    runtime: PlannerRuntime,
    warehouse: PlannerWarehouseState,
    scope: PlannerScope,
) -> tuple[RetentionPlanEntry, ...]:
    """Inspect managed selected retention scopes and produce independent plan entries."""

    selected_names: frozenset[str] = frozenset(
        key.name for key in scope.selected_keys if key.resource_type == CompiledResourceType.MODEL
    )
    selected_models: tuple[CompiledModel, ...] = tuple(
        model
        for model in runtime.project.models
        if model.name in selected_names
        and not model.config.time_travel_retention.unmanaged
        and model.config.time_travel_retention.desired_days is not None
    )
    if not selected_models:
        return ()
    if runtime.adapter.adapter_name == BuiltinAdapter.BIGQUERY:
        return _plan_bigquery_retention(runtime=runtime, models=selected_models)
    entries: list[RetentionPlanEntry] = []
    for model in selected_models:
        entries.extend(_plan_relation_retention(runtime=runtime, warehouse=warehouse, model=model))
    return tuple(entries)


def _plan_relation_retention(
    *, runtime: PlannerRuntime, warehouse: PlannerWarehouseState, model: CompiledModel
) -> tuple[RetentionPlanEntry, ...]:
    retention: ResolvedTimeTravelRetention = model.config.time_travel_retention
    if retention.desired_days is None or retention.source is None:
        raise PlannerInputError(f"model '{model.name}': managed retention is incomplete")
    desired_days: int = retention.desired_days
    source: str = retention.source.value
    schema: str | None = model.destination.schema
    if schema is None:
        raise PlannerInputError(f"model '{model.name}': retention requires a destination schema")
    request: RetentionRequest = RetentionRequest(
        request_id=model.name,
        scope=RetentionScope.RELATION,
        database=model.destination.database,
        schema=schema,
        name=model.destination.name,
        desired_days=desired_days,
    )
    if model.name not in warehouse.snapshot.existing_relations:
        if runtime.adapter.adapter_name == BuiltinAdapter.SNOWFLAKE and desired_days > 1:
            raise PlannerInputError(
                f"model '{model.name}': new Snowflake tables are transient and cannot retain "
                f"time travel for {desired_days} days; configure an explicit permanent-table "
                "migration before applying this policy"
            )
        changes: tuple[RenderedRetentionChange, ...] = runtime.adapter.render_retention_changes(
            request=request
        )
        return (
            _entry(
                request=request,
                model_names=(model.name,),
                state=None,
                source=source,
                direction=RetentionDirection.APPLY_AFTER_CREATE,
                phase=RetentionPlanPhase.AFTER_CREATE,
                statements=_flatten_changes(changes=changes),
            ),
        )
    state: RetentionState = runtime.adapter.inspect_retention(
        connection=runtime.connection, request=request
    )
    if state.is_transient and desired_days > 1:
        raise PlannerInputError(
            f"model '{model.name}': Snowflake transient tables cannot retain time travel for "
            f"{desired_days} days; use 0d or 1d, or make the table permanent"
        )
    direction: RetentionDirection = _state_direction(state=state, desired_days=desired_days)
    if direction == RetentionDirection.MATCH:
        return (
            _entry(
                request=request,
                model_names=(model.name,),
                state=state,
                source=source,
                direction=direction,
                phase=RetentionPlanPhase.NONE,
            ),
        )
    changes = runtime.adapter.render_retention_changes(request=request, state=state)
    return tuple(
        _entry(
            request=request,
            model_names=(model.name,),
            state=state,
            source=source,
            direction=_change_direction(change=change, fallback=direction),
            phase=_change_phase(change=change, fallback=direction),
            statements=change.statements,
        )
        for change in changes
    )


def _plan_bigquery_retention(
    *, runtime: PlannerRuntime, models: tuple[CompiledModel, ...]
) -> tuple[RetentionPlanEntry, ...]:
    target: TargetConfig = _effective_target(runtime=runtime)
    if not target.owns_time_travel_retention_namespace:
        raise PlannerInputError(
            "BigQuery managed time_travel_retention requires target "
            "owns_time_travel_retention_namespace = true"
        )
    all_managed: dict[tuple[str | None, str], list[CompiledModel]] = defaultdict(list)
    model: CompiledModel
    for model in runtime.project.models:
        retention: ResolvedTimeTravelRetention = model.config.time_travel_retention
        if (
            retention.unmanaged
            or retention.desired_days is None
            or model.destination.schema is None
        ):
            continue
        all_managed[(model.destination.database, model.destination.schema)].append(model)
    selected_scopes: set[tuple[str | None, str]] = {
        (model.destination.database, str(model.destination.schema)) for model in models
    }
    entries: list[RetentionPlanEntry] = []
    for database, schema in sorted(selected_scopes, key=lambda item: (item[0] or "", item[1])):
        scope_models: list[CompiledModel] = all_managed[(database, schema)]
        desired_values: set[int] = {
            desired
            for item in scope_models
            if (desired := item.config.time_travel_retention.desired_days) is not None
        }
        if len(desired_values) != 1:
            details: str = ", ".join(
                f"{item.name}={item.config.time_travel_retention.desired_days}d"
                for item in scope_models
            )
            raise PlannerInputError(
                f"BigQuery dataset {database + '.' if database else ''}{schema} has conflicting "
                f"managed retention values: {details}"
            )
        desired_days: int = desired_values.pop()
        sources: str = ",".join(
            sorted(
                {
                    source.value
                    for item in scope_models
                    if (source := item.config.time_travel_retention.source) is not None
                }
            )
        )
        request: RetentionRequest = RetentionRequest(
            request_id=f"{database + '.' if database else ''}{schema}",
            scope=RetentionScope.NAMESPACE,
            database=database,
            schema=schema,
            desired_days=desired_days,
        )
        state: RetentionState = runtime.adapter.inspect_retention(
            connection=runtime.connection, request=request
        )
        if not state.exists:
            changes: tuple[RenderedRetentionChange, ...] = runtime.adapter.render_retention_changes(
                request=request
            )
            entries.append(
                _entry(
                    request=request,
                    model_names=tuple(sorted(item.name for item in scope_models)),
                    state=state,
                    source=sources,
                    direction=RetentionDirection.APPLY_AFTER_CREATE,
                    phase=RetentionPlanPhase.PRE,
                    statements=_flatten_changes(changes=changes),
                )
            )
            continue
        direction: RetentionDirection = _state_direction(state=state, desired_days=desired_days)
        changes: tuple[RenderedRetentionChange, ...] = (
            ()
            if direction == RetentionDirection.MATCH
            else runtime.adapter.render_retention_changes(request=request, state=state)
        )
        statements: tuple[str, ...] = _flatten_changes(changes=changes)
        entries.append(
            _entry(
                request=request,
                model_names=tuple(sorted(item.name for item in scope_models)),
                state=state,
                source=sources,
                direction=direction,
                phase=(
                    RetentionPlanPhase.NONE
                    if direction == RetentionDirection.MATCH
                    else RetentionPlanPhase.PRE
                    if direction == RetentionDirection.INCREASE
                    else RetentionPlanPhase.POST
                ),
                statements=statements,
            )
        )
    return tuple(entries)


def _effective_target(*, runtime: PlannerRuntime) -> TargetConfig:
    if (
        runtime.project_config is None
        or runtime.local_config is None
        or runtime.project.effective_target_name is None
    ):
        return TargetConfig()
    return resolve_target_config(
        project_config=runtime.project_config,
        local_config=runtime.local_config,
        target_name=runtime.project.effective_target_name,
    )


def _flatten_changes(*, changes: tuple[RenderedRetentionChange, ...]) -> tuple[str, ...]:
    statements: list[str] = []
    for change in changes:
        statements.extend(change.statements)
    return tuple(statements)


def _state_direction(*, state: RetentionState, desired_days: int) -> RetentionDirection:
    values: tuple[int, ...] = tuple(
        value
        for value in (
            state.delta_log_retention_days,
            state.delta_deleted_file_retention_days,
        )
        if value is not None
    ) or (state.effective_days,)
    has_increase: bool = any(value < desired_days for value in values)
    has_decrease: bool = any(value > desired_days for value in values)
    if has_increase and has_decrease:
        return RetentionDirection.MIXED
    if has_increase:
        return RetentionDirection.INCREASE
    if has_decrease:
        return RetentionDirection.DECREASE
    return RetentionDirection.MATCH


def _change_direction(
    *, change: RenderedRetentionChange, fallback: RetentionDirection
) -> RetentionDirection:
    if change.phase == RetentionChangePhase.PREPARE:
        return RetentionDirection.INCREASE
    if change.phase == RetentionChangePhase.FINALIZE:
        return RetentionDirection.DECREASE
    return fallback


def _change_phase(
    *, change: RenderedRetentionChange, fallback: RetentionDirection
) -> RetentionPlanPhase:
    if change.phase == RetentionChangePhase.PREPARE:
        return RetentionPlanPhase.PRE
    if change.phase == RetentionChangePhase.FINALIZE:
        return RetentionPlanPhase.POST
    return (
        RetentionPlanPhase.PRE
        if fallback == RetentionDirection.INCREASE
        else RetentionPlanPhase.POST
    )


def _entry(
    *,
    request: RetentionRequest,
    model_names: tuple[str, ...],
    state: RetentionState | None,
    source: str,
    direction: RetentionDirection,
    phase: RetentionPlanPhase,
    statements: tuple[str, ...] = (),
) -> RetentionPlanEntry:
    return RetentionPlanEntry(
        request=request,
        model_names=model_names,
        actual_days=None if state is None else state.configured_days,
        effective_days=None if state is None else state.effective_days,
        source=source,
        direction=direction,
        phase=phase,
        statements=statements,
        irreversible_warning=(
            _DECREASE_WARNING if direction == RetentionDirection.DECREASE else None
        ),
    )
