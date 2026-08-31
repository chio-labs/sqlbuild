"""Direct build retention execution phases."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RenderedRetentionChange, RetentionState
from sqlbuild.adapter.contract.types import RetentionScope
from sqlbuild.compiler.planner.models import PlanOutput, RetentionPlanEntry
from sqlbuild.compiler.planner.types import RetentionPlanPhase


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
            _execute_statements(adapter=adapter, connection=connection, statements=entry.statements)


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
        state: RetentionState = adapter.inspect_retention(
            connection=connection, request=entry.request
        )
        if _state_matches(entry=entry, state=state):
            continue
        changes: tuple[RenderedRetentionChange, ...] = adapter.render_retention_changes(
            request=entry.request, state=state
        )
        change: RenderedRetentionChange
        for change in changes:
            _execute_statements(
                adapter=adapter, connection=connection, statements=change.statements
            )


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


def _execute_statements(
    *, adapter: BaseAdapter, connection: Any, statements: tuple[str, ...]
) -> None:
    statement: str
    for statement in statements:
        adapter.execute(connection=connection, sql=statement)
