"""Clone execution operations."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.planner.models import ModelPlanEntry, SeedPlanEntry
from sqlbuild.executor.clone.models import CloneItemResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus
from sqlbuild.shared.helpers.naming import resolve_target_qualified_name


def clone_relation(
    *,
    target_entry: SeedPlanEntry | ModelPlanEntry,
    source_entry: SeedPlanEntry | ModelPlanEntry,
    adapter: BaseAdapter,
    source_connection: Any,
    target_connection: Any,
    hard_copy: bool,
) -> CloneItemResult:
    if not relation_exists(adapter=adapter, connection=source_connection, entry=source_entry):
        return CloneItemResult(
            name=target_entry.name,
            action=CloneAction.WARNING_MISSING_SOURCE,
            status=CloneStatus.WARNING,
            message="missing in source environment",
        )

    recorder: StatementRecorder = StatementRecorder()
    target_qualified: str = qualified_name(adapter=adapter, entry=target_entry)
    source_qualified: str = qualified_name(adapter=adapter, entry=source_entry)
    try:
        adapter.drop(
            target_connection,
            target=target_qualified,
            if_exists=True,
            statement_recorder=recorder,
        )
        adapter.clone(
            target_connection,
            source=source_qualified,
            target=target_qualified,
            hard_copy=hard_copy,
            statement_recorder=recorder,
        )
    except Exception as exc:
        return CloneItemResult(
            name=target_entry.name,
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
        name=target_entry.name,
        action=action,
        status=CloneStatus.SUCCESS,
        executed_statements=recorder.snapshot(),
    )


def recreate_view(
    *,
    target_entry: ModelPlanEntry,
    source_entry: SeedPlanEntry | ModelPlanEntry,
    adapter: BaseAdapter,
    source_connection: Any,
    target_connection: Any,
) -> CloneItemResult:
    if not relation_exists(adapter=adapter, connection=source_connection, entry=source_entry):
        return CloneItemResult(
            name=target_entry.name,
            action=CloneAction.WARNING_MISSING_SOURCE,
            status=CloneStatus.WARNING,
            message="missing in source environment",
        )

    recorder: StatementRecorder = StatementRecorder()
    try:
        adapter.create_view_as(
            target_connection,
            target=qualified_name(adapter=adapter, entry=target_entry),
            sql=target_entry.resolved_sql,
            statement_recorder=recorder,
        )
    except Exception as exc:
        return CloneItemResult(
            name=target_entry.name,
            action=CloneAction.FAILED,
            status=CloneStatus.FAILED,
            message=str(exc),
            executed_statements=recorder.snapshot(),
        )
    return CloneItemResult(
        name=target_entry.name,
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
        database=entry.target.database,
        schema=entry.target.schema,
        name=entry.target.name,
    )


def qualified_name(*, adapter: BaseAdapter, entry: SeedPlanEntry | ModelPlanEntry) -> str:
    return resolve_target_qualified_name(adapter=adapter, target=entry.target)
