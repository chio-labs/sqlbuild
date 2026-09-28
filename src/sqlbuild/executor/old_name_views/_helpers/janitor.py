"""Janitor planning and execution for compatibility views at old model names."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.adapter.contract.types import RelationType
from sqlbuild.adapter.relations.main.resolve_qualified_name_parts import (
    resolve_qualified_name_parts,
)
from sqlbuild.adapter.type_system.main.normalize_relation_type import normalize_relation_type
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.migrations.constants import (
    MIGRATION_TABLE_NAME,
    OLD_NAME_VIEW_TABLE_NAME,
)
from sqlbuild.compiler.migrations.main.deterministic_old_name_view_event_id import (
    deterministic_old_name_view_event_id,
)
from sqlbuild.compiler.migrations.main.read_old_name_view_histories import (
    read_old_name_view_histories,
)
from sqlbuild.compiler.migrations.main.stored_old_name_view_columns import (
    stored_old_name_view_columns,
)
from sqlbuild.compiler.migrations.main.write_old_name_view_event import write_old_name_view_event
from sqlbuild.compiler.migrations.models import OldNameViewEvent, OldNameViewHistory
from sqlbuild.compiler.migrations.types import (
    OldNameViewDropReason,
    OldNameViewEventType,
    OldNameViewStatus,
)
from sqlbuild.executor.janitor.models import (
    JanitorOldNameView,
    JanitorOldNameViewPlanning,
    JanitorRelationKey,
    JanitorRelationScope,
)
from sqlbuild.executor.migrations.main._compatibility_view_sql import compatibility_view_sql


def plan_old_name_views(
    *,
    adapter: BaseAdapter,
    connection: Any,
    managed_target_schemas: set[tuple[str | None, str | None]],
    relations_by_schema: dict[tuple[str | None, str | None], tuple[RelationInfo, ...]],
    target_name: str | None,
    early_drops: tuple[str, ...],
    project_destinations: dict[JanitorRelationKey, str],
    now: datetime,
) -> JanitorOldNameViewPlanning:
    """Split recorded views into live, droppable, and gone; another relation's name is gone."""

    histories: tuple[OldNameViewHistory, ...] = tuple(
        history
        for history in _read_histories(
            adapter=adapter,
            connection=connection,
            managed_target_schemas=managed_target_schemas,
            relations_by_schema=relations_by_schema,
        )
        if history.move.target_name in (None, target_name)
        and history.status(now=now) in (OldNameViewStatus.LIVE, OldNameViewStatus.EXPIRED)
    )
    if not histories and not early_drops:
        return JanitorOldNameViewPlanning()
    physical: dict[JanitorRelationKey, RelationInfo] = _physical_old_names(
        adapter=adapter,
        connection=connection,
        histories=histories,
        relations_by_schema=relations_by_schema,
    )
    requested: dict[str, JanitorOldNameView | None] = dict.fromkeys(early_drops)
    live: list[JanitorOldNameView] = []
    drops: list[JanitorOldNameView] = []
    missing: list[JanitorOldNameView] = []
    history: OldNameViewHistory
    for history in histories:
        key: JanitorRelationKey = _old_key(history)
        view: JanitorOldNameView = _view(history)
        matched: tuple[str, ...] = tuple(name for name in requested if _names(name=name, key=key))
        requested.update(dict.fromkeys(matched, view))
        relation: RelationInfo | None = physical.get(key)
        if relation is None:
            missing.append(_with_reason(view=view, reason=OldNameViewDropReason.MISSING))
        elif not is_compatibility_view(
            adapter=adapter, connection=connection, view=view, relation=relation
        ):
            missing.append(_occupied(view=view, project_destinations=project_destinations))
        elif matched:
            drops.append(_with_reason(view=view, reason=OldNameViewDropReason.EARLY))
        elif history.status(now=now) == OldNameViewStatus.EXPIRED:
            drops.append(_with_reason(view=view, reason=OldNameViewDropReason.EXPIRED))
        else:
            live.append(view)
    return JanitorOldNameViewPlanning(
        live=tuple(live),
        drops=tuple(drops),
        missing=tuple(missing),
        unknown_requests=tuple(name for name, view in requested.items() if view is None),
        project_destinations=project_destinations,
    )


def protect_old_names(
    *, scope: JanitorRelationScope, old_names: JanitorOldNameViewPlanning
) -> JanitorRelationScope:
    """Keep general cleanup away from every old name this planning handles itself."""

    if not old_names.keys:
        return scope
    reasons: dict[JanitorRelationKey, str] = dict(scope.protected_relation_reasons or {})
    reasons.update({key: "compatibility view at an old model name" for key in old_names.keys})
    return replace(
        scope,
        protected_relation_keys=scope.protected_relation_keys | old_names.keys,
        protected_relation_reasons=reasons,
    )


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
    write_old_name_view_event(
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


def _read_histories(
    *,
    adapter: BaseAdapter,
    connection: Any,
    managed_target_schemas: set[tuple[str | None, str | None]],
    relations_by_schema: dict[tuple[str | None, str | None], tuple[RelationInfo, ...]],
) -> tuple[OldNameViewHistory, ...]:
    histories: list[OldNameViewHistory] = []
    database: str | None
    schema: str | None
    for database, schema in sorted(
        managed_target_schemas, key=lambda key: (key[0] or "", key[1] or "")
    ):
        names: frozenset[str] = frozenset(
            relation.name.lower() for relation in relations_by_schema.get((database, schema), ())
        )
        if schema is None or not {OLD_NAME_VIEW_TABLE_NAME, MIGRATION_TABLE_NAME} <= names:
            continue
        histories.extend(
            read_old_name_view_histories(
                connection=connection,
                execute=adapter.execute,
                database=database,
                schema=schema,
                stored_columns=stored_old_name_view_columns(
                    adapter=adapter, connection=connection, database=database, schema=schema
                ),
                render_qualified_name=adapter.render_qualified_name,
            )
        )
    return tuple(histories)


def _physical_old_names(
    *,
    adapter: BaseAdapter,
    connection: Any,
    histories: tuple[OldNameViewHistory, ...],
    relations_by_schema: dict[tuple[str | None, str | None], tuple[RelationInfo, ...]],
) -> dict[JanitorRelationKey, RelationInfo]:
    """Look up each old name, listing only schemas the janitor did not already scan."""

    known: dict[str, tuple[RelationInfo, ...]] = {
        (schema or "").lower(): relations for (_, schema), relations in relations_by_schema.items()
    }
    unscanned: tuple[OldNameViewHistory, ...] = tuple(
        history for history in histories if (history.old.schema or "").lower() not in known
    )
    listed: tuple[RelationInfo, ...] = (
        adapter.list_relations(
            connection=connection,
            database=unscanned[0].old.database,
            schemas=tuple(sorted({history.old.schema or "" for history in unscanned})),
            names=tuple(sorted({history.old.name for history in unscanned})),
        )
        if unscanned
        else ()
    )
    found: dict[JanitorRelationKey, RelationInfo] = {}
    scanned: list[RelationInfo] = list(listed)
    schema_relations: tuple[RelationInfo, ...]
    for schema_relations in known.values():
        scanned.extend(schema_relations)
    relation: RelationInfo
    for relation in scanned:
        _ = found.setdefault(
            JanitorRelationKey(
                database=relation.database, schema=relation.schema, name=relation.name
            ),
            relation,
        )
    physical: dict[JanitorRelationKey, RelationInfo] = {}
    history: OldNameViewHistory
    for history in histories:
        key: JanitorRelationKey = _old_key(history)
        match: RelationInfo | None = _lookup(found=found, key=key)
        if match is not None:
            physical[key] = match
    return physical


def _view(history: OldNameViewHistory) -> JanitorOldNameView:
    return JanitorOldNameView(
        key=_old_key(history),
        history=history,
        expires_at=None if history.created is None else history.created.expires_at,
    )


def project_destinations(project: CompiledProject) -> dict[JanitorRelationKey, str]:
    """Map each project model's destination to the model's name."""

    return {
        JanitorRelationKey(
            database=model.destination.database,
            schema=model.destination.schema,
            name=model.destination.name,
        ): model.name
        for model in project.models
    }


def _old_key(history: OldNameViewHistory) -> JanitorRelationKey:
    return JanitorRelationKey(
        database=history.old.database, schema=history.old.schema, name=history.old.name
    )


def _lookup(
    *, found: dict[JanitorRelationKey, RelationInfo], key: JanitorRelationKey
) -> RelationInfo | None:
    exact: RelationInfo | None = found.get(key)
    if exact is not None or key.database is not None:
        return exact
    return next(
        (
            relation
            for candidate, relation in found.items()
            if (candidate.schema or "").lower() == (key.schema or "").lower()
            and candidate.name.lower() == key.name.lower()
        ),
        None,
    )


def _names(*, name: str, key: JanitorRelationKey) -> bool:
    parts: list[str] = [part.strip().strip('"').lower() for part in name.split(".")]
    spelled: list[str] = [
        part.lower() for part in (key.database, key.schema, key.name) if part is not None
    ]
    return spelled[-len(parts) :] == parts


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


def _occupied(
    *, view: JanitorOldNameView, project_destinations: dict[JanitorRelationKey, str]
) -> JanitorOldNameView:
    return JanitorOldNameView(
        key=view.key,
        history=view.history,
        expires_at=view.expires_at,
        drop_reason=OldNameViewDropReason.MISSING,
        occupied=True,
        claimed_by=_claiming_model(key=view.key, project_destinations=project_destinations),
    )


def _claiming_model(
    *, key: JanitorRelationKey, project_destinations: dict[JanitorRelationKey, str]
) -> str | None:
    return next(
        (
            model_name
            for destination, model_name in project_destinations.items()
            if (destination.schema or "").lower() == (key.schema or "").lower()
            and destination.name.lower() == key.name.lower()
            and (
                destination.database is None
                or key.database is None
                or destination.database.lower() == key.database.lower()
            )
        ),
        None,
    )


def _is_view(relation: RelationInfo) -> bool:
    return normalize_relation_type(relation.relation_type) == RelationType.VIEW
