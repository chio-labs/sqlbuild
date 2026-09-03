"""Direct build retention execution phases."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationInfo, RenderedRetentionChange, RetentionState
from sqlbuild.adapter.contract.types import RetentionChangePhase, RetentionScope
from sqlbuild.adapter.relations.main.resolve_qualified_name_parts import (
    resolve_qualified_name_parts,
)
from sqlbuild.compiler.planner.models import PlanOutput, RetentionPlanEntry, TableTypePlanEntry
from sqlbuild.compiler.planner.types import RetentionPlanPhase
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.runtime.observability.classes.operation_lifecycle import (
    OperationAttributes,
    OperationLifecycle,
)
from sqlbuild.runtime.observability.main.canonicalize_operation_adapter import (
    canonicalize_operation_adapter,
)
from sqlbuild.spec.contracts.types import TableType


def apply_table_type_conversions(
    *, plan: PlanOutput, adapter: BaseAdapter, connection: Any
) -> None:
    """Recover by inspection: clean desired targets or recreate and swap undesired targets."""

    _apply_table_type_entries(
        entries=plan.table_type_entries, adapter=adapter, connection=connection
    )


def _apply_table_type_entries(
    *, entries: tuple[TableTypePlanEntry, ...], adapter: BaseAdapter, connection: Any
) -> None:
    if not entries:
        return
    _apply_table_type_entry(entry=entries[0], adapter=adapter, connection=connection)
    _apply_table_type_entries(entries=entries[1:], adapter=adapter, connection=connection)


def _apply_table_type_entry(
    *, entry: TableTypePlanEntry, adapter: BaseAdapter, connection: Any
) -> None:
    destination: str = resolve_qualified_name_parts(
        adapter=adapter,
        database=entry.destination.database,
        schema=entry.destination.schema,
        name=entry.destination.name,
    )
    copy: str = resolve_qualified_name_parts(
        adapter=adapter,
        database=entry.destination.database,
        schema=entry.destination.schema,
        name=entry.copy_name,
    )
    relations: dict[str, RelationInfo] = _inspect_table_type_entry(
        entry=entry, adapter=adapter, connection=connection
    )
    target: RelationInfo | None = relations.get(entry.destination.name.lower())
    if target is None:
        raise ExecutorInputError(
            f"model '{entry.model_name}': table-type conversion target no longer exists"
        )
    desired_transient: bool = entry.desired_type == TableType.TRANSIENT
    if target.is_transient is None:
        raise ExecutorInputError(
            f"model '{entry.model_name}': live table type metadata is unknown; refusing conversion"
        )
    if target.is_transient == desired_transient:
        if entry.copy_name.lower() in relations:
            with OperationLifecycle(
                operation_kind="warehouse",
                operation_name="table_type_conversion",
                attributes=OperationAttributes(
                    phase="convert",
                    adapter=canonicalize_operation_adapter(adapter.adapter_name),
                    target_kind="relation",
                ),
            ) as lifecycle:
                adapter.execute(connection=connection, sql=f"DROP TABLE IF EXISTS {copy}")
                lifecycle.completed(metadata={"changed_count": 1})
        return
    table_kind: str = "TRANSIENT TABLE" if desired_transient else "TABLE"
    with OperationLifecycle(
        operation_kind="warehouse",
        operation_name="table_type_conversion",
        attributes=OperationAttributes(
            phase="convert",
            adapter=canonicalize_operation_adapter(adapter.adapter_name),
            target_kind="relation",
        ),
    ) as lifecycle:
        adapter.execute(
            connection=connection,
            sql=f"CREATE OR REPLACE {table_kind} {copy} AS SELECT * FROM {destination}",
        )
        copy_info: RelationInfo | None = _inspect_table_type_entry(
            entry=entry, adapter=adapter, connection=connection
        ).get(entry.copy_name.lower())
        if copy_info is None or copy_info.is_transient is None:
            raise ExecutorInputError(
                f"model '{entry.model_name}': conversion copy type metadata is unknown"
            )
        if copy_info.is_transient != desired_transient:
            raise ExecutorInputError(
                f"model '{entry.model_name}': conversion copy was not created with the desired type"
            )
        adapter.execute(connection=connection, sql=f"ALTER TABLE {destination} SWAP WITH {copy}")
        adapter.execute(connection=connection, sql=f"DROP TABLE IF EXISTS {copy}")
        lifecycle.completed(metadata={"changed_count": 1})


def _inspect_table_type_entry(
    *, entry: TableTypePlanEntry, adapter: BaseAdapter, connection: Any
) -> dict[str, RelationInfo]:
    with OperationLifecycle(
        operation_kind="warehouse",
        operation_name="table_type_inspection",
        attributes=OperationAttributes(
            phase="inspect",
            adapter=canonicalize_operation_adapter(adapter.adapter_name),
            target_kind="relation",
        ),
    ) as lifecycle:
        relations: tuple[RelationInfo, ...] = adapter.list_relations(
            connection=connection,
            database=entry.destination.database,
            schemas=(entry.destination.schema,) if entry.destination.schema is not None else None,
            names=(entry.destination.name, entry.copy_name),
        )
        lifecycle.completed(metadata={"item_count": len(relations)})
    return {relation.name.lower(): relation for relation in relations}


def apply_retention_phase(
    *,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection: Any,
    phase: RetentionPlanPhase,
) -> None:
    """Execute one ordered plan-wide retention phase."""

    entry: RetentionPlanEntry
    for entry in plan.retention_entries:
        if entry.phase == phase:
            _apply_retention_statements(
                adapter=adapter,
                connection=connection,
                statements=entry.statements,
                target_kind=entry.request.scope.value,
            )


def reconcile_model_retention(
    *,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection: Any,
    model_name: str,
) -> None:
    """Reconcile a successfully materialized relation before item completion."""

    entry: RetentionPlanEntry
    for entry in plan.retention_entries:
        if model_name not in entry.model_names or entry.request.scope != RetentionScope.RELATION:
            continue
        state: RetentionState = _inspect_retention(
            adapter=adapter, connection=connection, entry=entry
        )
        if _state_matches(entry=entry, state=state):
            continue
        changes: tuple[RenderedRetentionChange, ...] = adapter.render_retention_changes(
            request=entry.request, state=state
        )
        change: RenderedRetentionChange
        for change in changes:
            if not _safe_before_build_success(entry=entry, state=state, change=change):
                continue
            _apply_retention_statements(
                adapter=adapter,
                connection=connection,
                statements=change.statements,
                target_kind=entry.request.scope.value,
            )


def reconcile_retention_after_build(
    *, plan: PlanOutput, adapter: BaseAdapter, connection: Any
) -> None:
    """Converge all remaining retention drift after the full build succeeds."""

    for entry in plan.retention_entries:
        if entry.phase == RetentionPlanPhase.NONE:
            continue
        state: RetentionState = _inspect_retention(
            adapter=adapter, connection=connection, entry=entry
        )
        if _state_matches(entry=entry, state=state):
            continue
        changes: tuple[RenderedRetentionChange, ...] = adapter.render_retention_changes(
            request=entry.request,
            state=state,
        )
        for change in changes:
            _apply_retention_statements(
                adapter=adapter,
                connection=connection,
                statements=change.statements,
                target_kind=entry.request.scope.value,
            )


def _safe_before_build_success(
    *, entry: RetentionPlanEntry, state: RetentionState, change: RenderedRetentionChange
) -> bool:
    if change.phase == RetentionChangePhase.FINALIZE:
        return False
    if change.phase == RetentionChangePhase.PREPARE:
        return True
    desired_days: int = entry.request.desired_days
    values: tuple[int, ...] = tuple(
        value
        for value in (
            state.delta_log_retention_days,
            state.delta_deleted_file_retention_days,
        )
        if value is not None
    ) or (state.effective_days,)
    return all(value <= desired_days for value in values)


def _state_matches(*, entry: RetentionPlanEntry, state: RetentionState) -> bool:
    desired_days: int = entry.request.desired_days
    values: tuple[int, ...] = tuple(
        value
        for value in (
            state.delta_log_retention_days,
            state.delta_deleted_file_retention_days,
        )
        if value is not None
    ) or (state.effective_days,)
    return all(value == desired_days for value in values)


def _inspect_retention(
    *, adapter: BaseAdapter, connection: Any, entry: RetentionPlanEntry
) -> RetentionState:
    with OperationLifecycle(
        operation_kind="warehouse",
        operation_name="retention_inspection",
        attributes=OperationAttributes(
            phase="inspect",
            adapter=canonicalize_operation_adapter(adapter.adapter_name),
            target_kind=entry.request.scope.value,
        ),
    ) as lifecycle:
        state: RetentionState = adapter.inspect_retention(
            connection=connection, request=entry.request
        )
        lifecycle.completed(
            metadata={"changed_count": int(not _state_matches(entry=entry, state=state))}
        )
        return state


def _apply_retention_statements(
    *,
    adapter: BaseAdapter,
    connection: Any,
    statements: tuple[str, ...],
    target_kind: str,
) -> None:
    if not statements:
        return
    with OperationLifecycle(
        operation_kind="warehouse",
        operation_name="retention_application",
        attributes=OperationAttributes(
            phase="apply",
            adapter=canonicalize_operation_adapter(adapter.adapter_name),
            target_kind=target_kind,
        ),
    ) as lifecycle:
        statement: str
        for statement in statements:
            adapter.execute(connection=connection, sql=statement)
        lifecycle.completed(metadata={"changed_count": len(statements)})
