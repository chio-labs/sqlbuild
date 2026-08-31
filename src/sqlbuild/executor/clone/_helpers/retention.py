"""Destination-only clone retention policy helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import (
    RenderedRetentionChange,
    RetentionRequest,
    RetentionState,
)
from sqlbuild.adapter.contract.types import BuiltinAdapter, RetentionScope
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.planner.types import RetentionPlanPhase
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.spec.contracts.models import ResolvedTimeTravelRetention


def build_clone_retention_requests(
    *,
    project: CompiledProject,
    adapter_name: str,
    namespace_owned: bool,
    selected_model_names: frozenset[str] | None = None,
) -> dict[str, RetentionRequest]:
    """Build requests exclusively from destination compiled model policies."""

    requests: dict[str, RetentionRequest] = {}
    selected_names: frozenset[str] = (
        frozenset(model.name for model in project.models)
        if selected_model_names is None
        else selected_model_names
    )
    selected_namespace_scopes: frozenset[tuple[str | None, str]] = frozenset(
        (model.destination.database, model.destination.schema)
        for model in project.models
        if model.name in selected_names and model.destination.schema is not None
    )
    namespace_values: dict[tuple[str | None, str], int] = {}
    for model in project.models:
        policy: ResolvedTimeTravelRetention = model.config.time_travel_retention
        if policy.unmanaged or policy.desired_days is None or model.destination.schema is None:
            continue
        if adapter_name == BuiltinAdapter.BIGQUERY:
            scope_key: tuple[str | None, str] = (
                model.destination.database,
                model.destination.schema,
            )
            if scope_key not in selected_namespace_scopes:
                continue
            if not namespace_owned:
                raise ExecutorInputError(
                    "BigQuery clone retention requires destination target "
                    "owns_time_travel_retention_namespace = true"
                )
            previous: int | None = namespace_values.get(scope_key)
            if previous is not None and previous != policy.desired_days:
                raise ExecutorInputError(
                    f"BigQuery destination dataset {scope_key} has conflicting retention values"
                )
            namespace_values[scope_key] = policy.desired_days
            if model.name not in selected_names:
                continue
            requests[model.name] = RetentionRequest(
                request_id=model.name,
                scope=RetentionScope.NAMESPACE,
                database=model.destination.database,
                schema=model.destination.schema,
                desired_days=policy.desired_days,
            )
            continue
        if model.name not in selected_names:
            continue
        requests[model.name] = RetentionRequest(
            request_id=model.name,
            scope=RetentionScope.RELATION,
            database=model.destination.database,
            schema=model.destination.schema,
            name=model.destination.name,
            desired_days=policy.desired_days,
        )
    return requests


def apply_clone_retention(
    *, request: RetentionRequest, adapter: BaseAdapter, connection: Any
) -> tuple[str, ...]:
    """Apply destination retention after clone creation."""

    state: RetentionState = adapter.inspect_retention(connection=connection, request=request)
    if state.is_transient and request.desired_days > 1:
        raise ExecutorInputError(
            "Snowflake transient clone destinations cannot retain time travel for more than 1 day"
        )
    values: tuple[int, ...] = tuple(
        value
        for value in (
            state.delta_log_retention_days,
            state.delta_deleted_file_retention_days,
        )
        if value is not None
    ) or (state.effective_days,)
    if all(value == request.desired_days for value in values):
        return ()
    changes: tuple[RenderedRetentionChange, ...] = adapter.render_retention_changes(
        request=request, state=state
    )
    executed: list[str] = []
    for change in changes:
        for statement in change.statements:
            adapter.execute(connection=connection, sql=statement)
            executed.append(statement)
    return tuple(executed)


def apply_clone_namespace_retention_phase(
    *,
    requests: dict[str, RetentionRequest],
    adapter: BaseAdapter,
    connection: Any,
    phase: RetentionPlanPhase,
) -> tuple[str, ...]:
    """Apply each destination namespace policy once in its safe clone phase."""

    namespace_requests: dict[tuple[str | None, str], RetentionRequest] = {
        (request.database, request.schema): request
        for request in requests.values()
        if request.scope == RetentionScope.NAMESPACE
    }
    executed: list[str] = []
    for request in namespace_requests.values():
        state: RetentionState = adapter.inspect_retention(connection=connection, request=request)
        should_apply: bool = (
            phase == RetentionPlanPhase.PRE and request.desired_days > state.effective_days
        ) or (phase == RetentionPlanPhase.POST and request.desired_days < state.effective_days)
        if not should_apply:
            continue
        changes: tuple[RenderedRetentionChange, ...] = adapter.render_retention_changes(
            request=request,
            state=state,
        )
        for change in changes:
            for statement in change.statements:
                adapter.execute(connection=connection, sql=statement)
                executed.append(statement)
    return tuple(executed)
