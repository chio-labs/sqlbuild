"""Clone execution operations."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.planner.models import ModelPlanEntry, SeedPlanEntry
from sqlbuild.executor.clone.models import CloneItemResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from sqlbuild.shared.helpers.naming import resolve_relation_location_qualified_name


def clone_relation(
    *,
    destination_entry: SeedPlanEntry | ModelPlanEntry,
    origin_entry: SeedPlanEntry | ModelPlanEntry,
    adapter: BaseAdapter,
    origin_connection: Any,
    destination_connection: Any,
    hard_copy: bool,
) -> CloneItemResult:
    if not relation_exists(adapter=adapter, connection=origin_connection, entry=origin_entry):
        return CloneItemResult(
            name=destination_entry.name,
            action=CloneAction.WARNING_MISSING_SOURCE,
            status=CloneStatus.WARNING,
            message="missing in origin environment",
        )

    recorder: StatementRecorder = StatementRecorder()
    destination_qualified: str = qualified_name(adapter=adapter, entry=destination_entry)
    origin_qualified: str = qualified_name(adapter=adapter, entry=origin_entry)
    try:
        adapter.drop(
            destination_connection,
            destination=destination_qualified,
            if_exists=True,
            statement_recorder=recorder,
        )
        adapter.clone(
            destination_connection,
            origin=origin_qualified,
            destination=destination_qualified,
            hard_copy=hard_copy,
            statement_recorder=recorder,
        )
    except Exception as exc:
        return CloneItemResult(
            name=destination_entry.name,
            action=CloneAction.FAILED,
            status=CloneStatus.FAILED,
            message=str(exc),
            executed_statements=recorder.snapshot(),
        )

    action: CloneAction = (
        CloneAction.COPIED
        if hard_copy or not adapter.supports_zero_copy_clone()
        else CloneAction.CLONED
    )
    return CloneItemResult(
        name=destination_entry.name,
        action=action,
        status=CloneStatus.SUCCESS,
        executed_statements=recorder.snapshot(),
    )


def recreate_view(
    *,
    destination_entry: ModelPlanEntry,
    origin_entry: SeedPlanEntry | ModelPlanEntry,
    adapter: BaseAdapter,
    origin_connection: Any,
    destination_connection: Any,
) -> CloneItemResult:
    if not relation_exists(adapter=adapter, connection=origin_connection, entry=origin_entry):
        return CloneItemResult(
            name=destination_entry.name,
            action=CloneAction.WARNING_MISSING_SOURCE,
            status=CloneStatus.WARNING,
            message="missing in origin environment",
        )

    recorder: StatementRecorder = StatementRecorder()
    try:
        adapter.create_view_as(
            destination_connection,
            destination=qualified_name(adapter=adapter, entry=destination_entry),
            sql=destination_entry.resolved_sql,
            statement_recorder=recorder,
        )
    except Exception as exc:
        return CloneItemResult(
            name=destination_entry.name,
            action=CloneAction.FAILED,
            status=CloneStatus.FAILED,
            message=str(exc),
            executed_statements=recorder.snapshot(),
        )
    return CloneItemResult(
        name=destination_entry.name,
        action=CloneAction.RECREATED_VIEW,
        status=CloneStatus.SUCCESS,
        executed_statements=recorder.snapshot(),
    )


def relation_exists(
    *,
    adapter: BaseAdapter,
    connection: Any,
    entry: SeedPlanEntry | ModelPlanEntry,
) -> bool:
    return adapter.relation_exists(
        connection,
        database=entry.destination.database,
        schema=entry.destination.schema,
        name=entry.destination.name,
    )


def qualified_name(*, adapter: BaseAdapter, entry: SeedPlanEntry | ModelPlanEntry) -> str:
    return resolve_relation_location_qualified_name(adapter=adapter, location=entry.destination)
