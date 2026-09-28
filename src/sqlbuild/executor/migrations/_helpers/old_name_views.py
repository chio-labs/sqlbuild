"""Archive old relations and keep compatibility views at old model names."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import ColumnInfo, RelationInfo
from sqlbuild.adapter.contract.types import RelationType
from sqlbuild.adapter.relations.main.resolve_qualified_name_parts import (
    resolve_qualified_name_parts,
)
from sqlbuild.adapter.type_system.main.normalize_relation_type import normalize_relation_type
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.migrations.constants import COLUMN_MIGRATION_TABLE_NAME
from sqlbuild.compiler.migrations.main.deterministic_event_id import (
    deterministic_migration_event_id,
)
from sqlbuild.compiler.migrations.main.read_recorded_column_renames import (
    read_recorded_column_renames,
)
from sqlbuild.compiler.migrations.main.relation_for_location import migration_relation_for_location
from sqlbuild.compiler.migrations.models import (
    ColumnMigrationEvent,
    MigrationRelation,
    OldNameViewEvent,
)
from sqlbuild.compiler.migrations.types import OldNameViewEventType
from sqlbuild.compiler.planner.models import OldNameView, OldNameViewPlanEntry, PlanOutput
from sqlbuild.cursor_algebra.models import Duration
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.janitor.main._build_archive_name import build_janitor_archive_name
from sqlbuild.executor.migrations._helpers.old_name_facts import (
    old_name_fact,
    record_old_name_fact,
    recorded_old_name_facts,
)
from sqlbuild.executor.migrations.constants import (
    MIGRATION_NAME_ATTEMPTS,
    MIGRATION_ORIGIN_ARCHIVE_KIND,
)
from sqlbuild.executor.migrations.models import OldNameViewSource


def run_old_name_steps(
    *,
    adapter: BaseAdapter,
    connection: Any,
    entry: OldNameViewPlanEntry,
    migration_event_id: str,
    run_id: str,
    recorded_views: tuple[OldNameView, ...],
) -> tuple[str, ...]:
    """Archive the old relation and create its compatibility view, resuming from facts."""

    facts: dict[OldNameViewEventType, OldNameViewEvent] = recorded_old_name_facts(
        adapter=adapter, connection=connection, entry=entry, migration_event_id=migration_event_id
    )
    required: OldNameViewEvent | None = facts.get(OldNameViewEventType.REQUIRED)
    if required is None or OldNameViewEventType.VIEW_CREATED in facts:
        return ()
    aliases: tuple[tuple[str, str], ...] = (
        _recorded_column_aliases(
            adapter=adapter, connection=connection, entry=entry, since=required
        )
        if entry.stores_history
        else entry.column_aliases
    )
    source: OldNameViewSource = OldNameViewSource(
        old=entry.origin, new=entry.destination, column_aliases=aliases
    )
    select_sql: str = render_old_name_view_select(
        adapter=adapter, connection=connection, source=source
    )
    old_relation: RelationInfo | None = _listed(
        adapter=adapter, connection=connection, location=entry.origin
    )
    archived: bool = OldNameViewEventType.ORIGIN_ARCHIVED in facts
    if archived and old_relation is not None and not _is_view(old_relation):
        return (
            f"M116: {_display(entry.origin)} is held by another relation after it was archived; "
            "no compatibility view was created",
        )
    warnings: tuple[str, ...] = ()
    if not archived and old_relation is not None and adapter.views_bind_to_relation_identity():
        warnings = _external_dependents_warning(
            adapter=adapter, connection=connection, entry=entry, recorded_views=recorded_views
        )
    chained: tuple[OldNameViewSource, ...] = _chained_sources(
        location=entry.origin, recorded_views=recorded_views
    )
    now: datetime = datetime.now(tz=UTC)
    duration: Duration | None = Duration.parse(required.view_retention or "")
    with _ddl_transaction(adapter=adapter, connection=connection) as transactional:
        attempts: int = 1 if transactional else 3
        if not archived:
            archive_name: str | None = _archive_old_relation(
                adapter=adapter, connection=connection, entry=entry, old_relation=old_relation
            )
            record_old_name_fact(
                adapter=adapter,
                connection=connection,
                event=old_name_fact(
                    entry=entry,
                    event_type=OldNameViewEventType.ORIGIN_ARCHIVED,
                    migration_event_id=migration_event_id,
                    run_id=run_id,
                    created_at=now,
                    archive_name=archive_name,
                ),
                create_table=False,
                attempts=attempts,
            )
        _create_compatibility_view(
            adapter=adapter, connection=connection, entry=entry, sql=select_sql
        )
        record_old_name_fact(
            adapter=adapter,
            connection=connection,
            event=old_name_fact(
                entry=entry,
                event_type=OldNameViewEventType.VIEW_CREATED,
                migration_event_id=migration_event_id,
                run_id=run_id,
                created_at=now,
                column_aliases=aliases,
                expires_at=None if duration is None else duration.add_to(now),
            ),
            create_table=False,
            attempts=attempts,
        )
        _ = refresh_old_name_views(adapter=adapter, connection=connection, sources=chained)
    return warnings


def run_planned_old_name_steps(
    *, plan: PlanOutput, adapter: BaseAdapter, connection: Any, model_name: str, run_id: str
) -> tuple[str, ...]:
    """Run every pending old-name step planned for one successfully built model."""

    warnings: list[str] = []
    entry: OldNameViewPlanEntry
    for entry in plan.old_name_view_entries:
        if entry.model_name != model_name or not entry.runs_steps:
            continue
        try:
            warnings.extend(
                run_old_name_steps(
                    adapter=adapter,
                    connection=connection,
                    entry=entry,
                    migration_event_id=_migration_event_id(entry=entry, run_id=run_id),
                    run_id=run_id,
                    recorded_views=plan.old_name_views,
                )
            )
        except Exception as error:
            raise ExecutorInputError(
                f"model '{model_name}': keeping its old name {_display(entry.origin)} "
                f"failed: {error}",
                code="M117",
                help=(
                    "Re-run the build; old-name steps resume from recorded facts and never "
                    "repeat a completed step."
                ),
            ) from error
    return tuple(warnings)


def refresh_old_name_views(
    *, adapter: BaseAdapter, connection: Any, sources: tuple[OldNameViewSource, ...]
) -> int:
    """Re-create compatibility views in order, each against its source's current columns."""

    source: OldNameViewSource
    for source in sources:
        _create_view(
            adapter=adapter,
            connection=connection,
            old=source.old,
            sql=render_old_name_view_select(adapter=adapter, connection=connection, source=source),
        )
    return len(sources)


def drop_old_name_views(
    *, adapter: BaseAdapter, connection: Any, sources: tuple[OldNameViewSource, ...]
) -> int:
    """Drop compatibility views, dependents first, when they exist."""

    source: OldNameViewSource
    for source in reversed(sources):
        adapter.drop_view(
            connection=connection,
            destination=_qualified(adapter=adapter, location=source.old),
            if_exists=True,
            statement_recorder=StatementRecorder(),
        )
    return len(sources)


def _migration_event_id(*, entry: OldNameViewPlanEntry, run_id: str) -> str:
    if entry.migration_event_id is not None:
        return entry.migration_event_id
    return deterministic_migration_event_id(
        run_id=run_id,
        target_name=entry.target_name,
        origin=migration_relation_for_location(entry.origin),
        destination=migration_relation_for_location(entry.destination),
    )


def views_reading(
    *, location: CompiledRelationLocation, recorded_views: tuple[OldNameView, ...]
) -> tuple[OldNameViewSource, ...]:
    """Return recorded views that read one relation, then views chained onto those, in order."""

    ordered: list[OldNameViewSource] = []
    seen: set[tuple[str | None, str, str]] = set()
    frontier: list[CompiledRelationLocation] = [location]
    while frontier:
        current: CompiledRelationLocation = frontier.pop(0)
        view: OldNameView
        for view in _direct_readers(location=current, recorded_views=recorded_views):
            identity: tuple[str | None, str, str] = migration_relation_for_location(
                view.old
            ).identity
            if identity in seen:
                continue
            seen.add(identity)
            ordered.append(
                OldNameViewSource(old=view.old, new=view.new, column_aliases=view.column_aliases)
            )
            frontier.append(view.old)
    return tuple(ordered)


def render_old_name_view_select(
    *, adapter: BaseAdapter, connection: Any, source: OldNameViewSource
) -> str:
    """Render the SELECT that presents the new relation under the old interface."""

    relation: str = _qualified(adapter=adapter, location=source.new)
    if not source.column_aliases:
        return f"SELECT * FROM {relation}"
    columns: tuple[ColumnInfo, ...] = adapter.get_columns(
        connection=connection,
        database=source.new.database,
        schema=source.new.schema,
        name=source.new.name,
    )
    old_by_new: dict[str, str] = {new.lower(): old for old, new in source.column_aliases}
    projections: list[str] = []
    column: ColumnInfo
    for column in columns:
        rendered: str = adapter.render_exact_identifier(column.name)
        old_name: str | None = old_by_new.get(column.name.lower())
        projections.append(
            rendered if old_name is None else f"{rendered} AS {adapter.render_identifier(old_name)}"
        )
    return f"SELECT {', '.join(projections)} FROM {relation}"


def compose_column_aliases(
    events: tuple[ColumnMigrationEvent, ...],
) -> tuple[tuple[str, str], ...]:
    """Fold ordered column renames into one old-name-to-current-name map."""

    current_by_old: dict[str, str] = {}
    event: ColumnMigrationEvent
    for event in sorted(events, key=lambda item: (item.created_at, item.event_id)):
        origin: str = event.origin_column
        replaced: bool = False
        old: str
        for old, current in tuple(current_by_old.items()):
            if current.lower() == origin.lower():
                current_by_old[old] = event.destination_column
                replaced = True
        if not replaced:
            current_by_old[origin] = event.destination_column
    return tuple(
        sorted((old, new) for old, new in current_by_old.items() if old.lower() != new.lower())
    )


def _recorded_column_aliases(
    *, adapter: BaseAdapter, connection: Any, entry: OldNameViewPlanEntry, since: OldNameViewEvent
) -> tuple[tuple[str, str], ...]:
    relation: MigrationRelation = migration_relation_for_location(entry.destination)
    if not adapter.list_relations(
        connection=connection,
        database=relation.database,
        schemas=(relation.schema or "",),
        names=(COLUMN_MIGRATION_TABLE_NAME,),
    ):
        return ()
    return compose_column_aliases(
        read_recorded_column_renames(
            connection=connection,
            execute=adapter.execute,
            relation=relation,
            since=since.created_at,
            render_qualified_name=adapter.render_qualified_name,
        )
    )


def _archive_old_relation(
    *,
    adapter: BaseAdapter,
    connection: Any,
    entry: OldNameViewPlanEntry,
    old_relation: RelationInfo | None,
) -> str | None:
    if old_relation is None:
        return _existing_archive_name(adapter=adapter, connection=connection, entry=entry)
    archive_name: str = _unused_archive_name(adapter=adapter, connection=connection, entry=entry)
    origin: str = _qualified(adapter=adapter, location=entry.origin)
    destination: str = resolve_qualified_name_parts(
        adapter=adapter,
        database=entry.origin.database,
        schema=entry.origin.schema,
        name=archive_name,
    )
    if _is_view(old_relation):
        statement: str
        for statement in adapter.render_rename_view(origin=origin, destination=destination):
            _ = adapter.execute(connection=connection, sql=statement)
    else:
        adapter.rename(
            connection=connection,
            origin=origin,
            destination=destination,
            statement_recorder=StatementRecorder(),
        )
    return archive_name


def _unused_archive_name(
    *, adapter: BaseAdapter, connection: Any, entry: OldNameViewPlanEntry
) -> str:
    now: datetime = datetime.now(tz=UTC)
    candidates: tuple[str, ...] = tuple(
        build_janitor_archive_name(
            original_name=entry.origin.name,
            archived_at=now - timedelta(seconds=offset),
            identifier_limit=adapter.maximum_identifier_length(),
            kind=MIGRATION_ORIGIN_ARCHIVE_KIND,
        )
        for offset in range(MIGRATION_NAME_ATTEMPTS)
    )
    existing: frozenset[str] = frozenset(
        relation.name.lower()
        for relation in adapter.list_relations(
            connection=connection,
            database=entry.origin.database,
            schemas=(entry.origin.schema or "",),
            names=candidates,
        )
    )
    name: str
    for name in candidates:
        if name not in existing:
            return name
    return candidates[0]


def _existing_archive_name(
    *, adapter: BaseAdapter, connection: Any, entry: OldNameViewPlanEntry
) -> str | None:
    """Find the archive an interrupted run left, as physical evidence for the archive fact."""

    suffix: str = f"__{MIGRATION_ORIGIN_ARCHIVE_KIND}__{entry.origin.name}".lower()
    names: list[str] = sorted(
        relation.name.lower()
        for relation in adapter.list_relations(
            connection=connection,
            database=entry.origin.database,
            schemas=(entry.origin.schema or "",),
            names=None,
        )
        if relation.name.lower().startswith("_sqb_archive__")
        and relation.name.lower().endswith(suffix)
    )
    return names[-1] if names else None


def _external_dependents_warning(
    *,
    adapter: BaseAdapter,
    connection: Any,
    entry: OldNameViewPlanEntry,
    recorded_views: tuple[OldNameView, ...],
) -> tuple[str, ...]:
    owned: frozenset[str] = frozenset(
        f"{view.old.schema}.{view.old.name}".lower() for view in recorded_views
    )
    dependents: tuple[str, ...] = tuple(
        name
        for name in adapter.list_dependent_view_names(
            connection=connection,
            database=entry.origin.database,
            schema=entry.origin.schema or "",
            name=entry.origin.name,
        )
        if name.lower() not in owned
    )
    if not dependents:
        return ()
    return (
        f"M115: views not managed by SQLBuild depend on {_display(entry.origin)}: "
        f"{', '.join(dependents)}. They stay bound to the archived relation and keep reading "
        "its old data; re-create them against the old name, now a compatibility view, or "
        f"against {_display(entry.destination)}",
    )


def _chained_sources(
    *, location: CompiledRelationLocation, recorded_views: tuple[OldNameView, ...]
) -> tuple[OldNameViewSource, ...]:
    return views_reading(location=location, recorded_views=recorded_views)


def _direct_readers(
    *, location: CompiledRelationLocation, recorded_views: tuple[OldNameView, ...]
) -> tuple[OldNameView, ...]:
    relation: MigrationRelation = migration_relation_for_location(location)
    return tuple(
        view
        for view in recorded_views
        if migration_relation_for_location(view.new).matches(relation)
    )


def _create_compatibility_view(
    *, adapter: BaseAdapter, connection: Any, entry: OldNameViewPlanEntry, sql: str
) -> None:
    """Publish the view at the old name inside the step that records ``view_created``."""

    _create_view(adapter=adapter, connection=connection, old=entry.origin, sql=sql)


def _create_view(
    *, adapter: BaseAdapter, connection: Any, old: CompiledRelationLocation, sql: str
) -> None:
    statement: str
    for statement in adapter.render_create_view_as(
        destination=_qualified(adapter=adapter, location=old), sql=sql
    ):
        _ = adapter.execute(connection=connection, sql=statement)


def _listed(
    *, adapter: BaseAdapter, connection: Any, location: CompiledRelationLocation
) -> RelationInfo | None:
    wanted: tuple[str, str] = ((location.schema or "").lower(), location.name.lower())
    return next(
        (
            relation
            for relation in adapter.list_relations(
                connection=connection,
                database=location.database,
                schemas=(location.schema or "",),
                names=(location.name,),
            )
            if ((relation.schema or "").lower(), relation.name.lower()) == wanted
        ),
        None,
    )


def _is_view(relation: RelationInfo) -> bool:
    return normalize_relation_type(relation.relation_type) == RelationType.VIEW


@contextlib.contextmanager
def _ddl_transaction(*, adapter: BaseAdapter, connection: Any) -> Iterator[bool]:
    if not adapter.supports_transactional_ddl():
        yield False
        return
    with adapter.transaction(connection):
        yield True


def _qualified(*, adapter: BaseAdapter, location: CompiledRelationLocation) -> str:
    return location.qualified_name or resolve_qualified_name_parts(
        adapter=adapter, database=location.database, schema=location.schema, name=location.name
    )


def _display(location: CompiledRelationLocation) -> str:
    return location.qualified_name or location.name
