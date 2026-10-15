"""Janitor planning and execution for compatibility views at old model names."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlbuild._native import (
    OldNameViewDropReason,
    OldNameViewEvent,
    OldNameViewEventType,
    deterministic_old_name_view_event_id,
    write_migration_state_event,
)
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.adapter.contract.types import RelationType
from sqlbuild.adapter.relations.main.resolve_qualified_name_parts import (
    resolve_qualified_name_parts,
)
from sqlbuild.adapter.type_system.main.normalize_relation_type import normalize_relation_type
from sqlbuild.executor.janitor.models import (
    JanitorOldNameView,
    JanitorOldNameViewPlanning,
    JanitorRelationKey,
)
from sqlbuild.executor.migrations.main._compatibility_view_sql import compatibility_view_sql


def apply_old_name_view_drops(
    *,
    plan: JanitorOldNameViewPlanning,
    adapter: BaseAdapter,
    connection: Any,
    recorder: StatementRecorder,
    run_id: str,
) -> tuple[JanitorOldNameView, ...]:
    """Drop expired or requested views, then record every drop and every vanished view."""

    dropped: list[JanitorOldNameView] = []
    view: JanitorOldNameView
    for view in plan.drops:
        if not is_compatibility_view(adapter=adapter, connection=connection, view=view):
            _record_drop(
                adapter=adapter,
                connection=connection,
                view=_with_reason(view=view, reason=OldNameViewDropReason.MISSING),
                run_id=run_id,
            )
            continue
        adapter.drop_view(
            connection=connection,
            destination=resolve_qualified_name_parts(
                adapter=adapter,
                database=view.key.database,
                schema=view.key.schema,
                name=view.key.name,
            ),
            if_exists=True,
            statement_recorder=recorder,
        )
        _record_drop(adapter=adapter, connection=connection, view=view, run_id=run_id)
        dropped.append(view)
    for view in plan.missing:
        _record_drop(adapter=adapter, connection=connection, view=view, run_id=run_id)
    return tuple(dropped)


def _record_drop(
    *, adapter: BaseAdapter, connection: Any, view: JanitorOldNameView, run_id: str
) -> None:
    required: OldNameViewEvent = view.history.required
    write_migration_state_event(
        kind="old_name",
        connection=connection,
        execute=adapter.execute,
        event=OldNameViewEvent(
            event_id=deterministic_old_name_view_event_id(
                event_type=OldNameViewEventType.VIEW_DROPPED,
                migration_event_id=required.migration_event_id,
            ),
            target_name=required.target_name,
            event_type=OldNameViewEventType.VIEW_DROPPED,
            migration_event_id=required.migration_event_id,
            destination_model=required.destination_model,
            old=required.old,
            new=required.new,
            run_id=run_id,
            created_at=datetime.now(tz=UTC),
            drop_reason=view.drop_reason,
        ),
        render_qualified_name=adapter.render_qualified_name,
        create_table_sql=adapter.render_create_old_name_view_state_table_sql(
            database=required.new.database, schema=required.new.schema or ""
        ),
    )


def _with_reason(*, view: JanitorOldNameView, reason: OldNameViewDropReason) -> JanitorOldNameView:
    return JanitorOldNameView(
        key=view.key, history=view.history, expires_at=view.expires_at, drop_reason=reason
    )


def is_compatibility_view(
    *,
    adapter: BaseAdapter,
    connection: Any,
    view: JanitorOldNameView,
    relation: RelationInfo | None = None,
) -> bool:
    """Return whether the relation at the old name is still the view SQLBuild defined there."""

    listed: RelationInfo | None = relation or _listed_relation(
        adapter=adapter, connection=connection, key=view.key
    )
    if listed is None or not _is_view(listed) or view.key.schema is None:
        return False
    schema: str = view.key.schema
    return any(
        adapter.view_definition_matches(
            connection=connection,
            database=view.key.database,
            schema=schema,
            name=view.key.name,
            sql=sql,
        )
        for sql in compatibility_view_sql(
            adapter=adapter, connection=connection, history=view.history
        )
    )


def _listed_relation(
    *, adapter: BaseAdapter, connection: Any, key: JanitorRelationKey
) -> RelationInfo | None:
    return next(
        (
            relation
            for relation in adapter.list_relations(
                connection=connection,
                database=key.database,
                schemas=(key.schema or "",),
                names=(key.name,),
            )
            if relation.name.lower() == key.name.lower()
        ),
        None,
    )


def _is_view(relation: RelationInfo) -> bool:
    return normalize_relation_type(relation.relation_type) == RelationType.VIEW
