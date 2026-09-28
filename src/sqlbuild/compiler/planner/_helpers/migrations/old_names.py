"""Plan what a build does at migrated models' old names."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.adapter.contract.types import RelationType
from sqlbuild.adapter.type_system.main.normalize_relation_type import normalize_relation_type
from sqlbuild.compiler.compile.models import CompiledModel, CompiledRelationLocation
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.migrations.main._resolve_old_name_view_retention import (
    resolve_old_name_view_retention,
)
from sqlbuild.compiler.migrations.main.relation_for_location import migration_relation_for_location
from sqlbuild.compiler.migrations.models import MigrationRelation, OldNameViewHistory
from sqlbuild.compiler.migrations.types import (
    ColumnMigrationDecision,
    MigrationDecision,
    OldNameViewAction,
    OldNameViewStatus,
)
from sqlbuild.compiler.planner._helpers.migrations.planning import (
    planning_database,
    project_schemas,
)
from sqlbuild.compiler.planner.classes.migration_state_inspection import (
    MigrationStateInspection,
)
from sqlbuild.compiler.planner.models import (
    ColumnMigrationPlanEntry,
    ModelMigrationPlanEntry,
    OldNameView,
    OldNameViewPlanEntry,
    OldNameViewPlanning,
    PlannerRuntime,
    PlannerScope,
    PlanWarning,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import MaterializationType, WarningSeverity
from sqlbuild.compiler.references.main._old_name_reference_message import (
    old_name_reference_message,
)
from sqlbuild.compiler.references.main.hard_coded_relation_remedy import (
    hard_coded_relation_remedy,
)
from sqlbuild.compiler.references.main.match_project_relation import match_project_relation
from sqlbuild.compiler.references.models import (
    LiteralSqlRelation,
    ProjectRelation,
    ProjectRelationIndex,
    RelationName,
)
from sqlbuild.cursor_algebra.models import Duration
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind
from sqlbuild.spec.contracts.main.get_config_str import get_config_str
from sqlbuild.spec.contracts.models import MigrationsConfig, SchemaColumn

_HISTORY_MATERIALIZATIONS: frozenset[str] = frozenset(
    {MaterializationType.INCREMENTAL, MaterializationType.SNAPSHOT}
)
_ALIAS_DECISIONS: frozenset[ColumnMigrationDecision] = frozenset(
    {ColumnMigrationDecision.RENAME, ColumnMigrationDecision.RECORD}
)
_RESUMED_STATUSES: frozenset[OldNameViewStatus] = frozenset(
    {OldNameViewStatus.PENDING_ARCHIVE, OldNameViewStatus.PENDING_VIEW}
)
_PENDING_ACTIONS: dict[OldNameViewStatus, OldNameViewAction] = {
    OldNameViewStatus.PENDING_ARCHIVE: OldNameViewAction.ARCHIVE_AND_VIEW,
    OldNameViewStatus.PENDING_VIEW: OldNameViewAction.VIEW_ONLY,
    OldNameViewStatus.LIVE: OldNameViewAction.LIVE,
    OldNameViewStatus.EXPIRED: OldNameViewAction.LIVE,
}


def plan_old_name_views(
    *,
    runtime: PlannerRuntime,
    scope: PlannerScope,
    snapshot: WarehouseSnapshot,
    migration_entries: tuple[ModelMigrationPlanEntry, ...],
    column_entries: tuple[ColumnMigrationPlanEntry, ...],
) -> OldNameViewPlanning:
    """Decide old-name steps for selected models and collect recorded compatibility views."""

    models_by_name: dict[str, CompiledModel] = {
        model.name: model for model in runtime.project.models
    }
    selected: tuple[CompiledModel, ...] = tuple(
        models_by_name[key.name]
        for key in scope.execution_order
        if key in scope.selected_keys
        and key.resource_type == CompiledResourceType.MODEL
        and key.name in models_by_name
    )
    state: MigrationStateInspection = MigrationStateInspection(
        adapter=runtime.adapter,
        connection=runtime.connection,
        database=planning_database(runtime=runtime),
    )
    schemas: set[str] = _schemas_to_read(
        snapshot=snapshot,
        needed=_needed_schemas(
            runtime=runtime,
            selected=selected,
            snapshot=snapshot,
            migration_entries=migration_entries,
        ),
    )
    if schemas:
        state.inspect_old_name_views(schemas=schemas)
    target_name: str | None = runtime.project.effective_target_name
    histories: tuple[OldNameViewHistory, ...] = tuple(
        history
        for history in state.old_name_histories
        if history.move.target_name in (None, target_name)
    )
    views: tuple[OldNameView, ...] = tuple(
        _recorded_view(runtime=runtime, history=history, models=runtime.project.models)
        for history in histories
        if history.created is not None and history.dropped is None
    )
    planner: _OldNamePlanner = _OldNamePlanner(
        runtime=runtime,
        models_by_name=models_by_name,
        histories=histories,
        views=views,
        column_entries=column_entries,
    )
    entries: list[OldNameViewPlanEntry] = []
    covered: set[str] = set()
    entry: ModelMigrationPlanEntry
    for entry in migration_entries:
        planned: OldNameViewPlanEntry | None = planner.for_migration(entry)
        if planned is not None:
            entries.append(planned)
            covered.add(entry.model_name)
    model: CompiledModel
    for model in selected:
        if model.name in covered:
            continue
        pending: OldNameViewPlanEntry | None = planner.pending_for(model)
        if pending is not None:
            entries.append(pending)
    return OldNameViewPlanning(
        entries=tuple(entries),
        views=views,
        warnings=(
            *_claim_errors(
                selected=selected, snapshot=snapshot, views=views, now=runtime.invocation_time
            ),
            *_old_name_reference_errors(runtime=runtime, views=views, entries=tuple(entries)),
        ),
    )


class _OldNamePlanner:
    """Per-plan inputs shared by every old-name decision."""

    def __init__(
        self,
        *,
        runtime: PlannerRuntime,
        models_by_name: dict[str, CompiledModel],
        histories: tuple[OldNameViewHistory, ...],
        views: tuple[OldNameView, ...],
        column_entries: tuple[ColumnMigrationPlanEntry, ...],
    ) -> None:
        self._runtime: PlannerRuntime = runtime
        self._models_by_name: dict[str, CompiledModel] = models_by_name
        self._histories: tuple[OldNameViewHistory, ...] = histories
        self._views: tuple[OldNameView, ...] = views
        self._column_entries: tuple[ColumnMigrationPlanEntry, ...] = column_entries
        config: MigrationsConfig = (
            runtime.project_config.migrations
            if runtime.project_config is not None
            else MigrationsConfig()
        )
        self._project_retention: str | None = config.old_name_views
        self._now: datetime = runtime.invocation_time

    def for_migration(self, entry: ModelMigrationPlanEntry) -> OldNameViewPlanEntry | None:
        model: CompiledModel | None = self._models_by_name.get(entry.model_name)
        if model is None or entry.blocks_build:
            return None
        if _starts_move(entry):
            return self._new_move(entry=entry, model=model)
        if entry.decision == MigrationDecision.DONE or (
            entry.decision == MigrationDecision.RENAMED and entry.completed_at is not None
        ):
            history: OldNameViewHistory | None = self._newest_history(
                destination=migration_relation_for_location(entry.destination),
                origin=migration_relation_for_location(entry.origin),
            )
            return None if history is None else self._from_history(history=history, model=model)
        return None

    def pending_for(self, model: CompiledModel) -> OldNameViewPlanEntry | None:
        history: OldNameViewHistory | None = self._newest_history(
            destination=migration_relation_for_location(model.destination), origin=None
        )
        if history is None or history.move.destination_model != model.name:
            return None
        planned: OldNameViewPlanEntry | None = self._from_history(history=history, model=model)
        if planned is None or not (planned.runs_steps or _skips_pending(planned)):
            return None
        return planned

    def _new_move(
        self, *, entry: ModelMigrationPlanEntry, model: CompiledModel
    ) -> OldNameViewPlanEntry:
        retention: str | None = resolve_old_name_view_retention(
            config_values=model.config.values, project_retention=self._project_retention
        )
        reason: str | None = self._skip_reason(
            origin=entry.origin, origin_tracked=entry.origin_tracked, retention=retention
        )
        if reason is not None or retention is None:
            return _skipped_entry(entry=entry, reason=reason or "old_name_view false")
        duration: Duration | None = Duration.parse(retention)
        return OldNameViewPlanEntry(
            model_name=entry.model_name,
            origin=entry.origin,
            destination=entry.destination,
            action=OldNameViewAction.ARCHIVE_AND_VIEW,
            target_name=entry.target_name,
            retention=retention,
            expires_at=None if duration is None else duration.add_to(self._now),
            column_aliases=self._planned_aliases(model),
            stores_history=_stores_history(model),
            records_requirement=True,
            grants_supported=self._runtime.adapter.relation_grants_supported,
        )

    def _skip_reason(
        self,
        *,
        origin: CompiledRelationLocation,
        origin_tracked: bool | None,
        retention: str | None,
    ) -> str | None:
        """Return why the old name gets no steps; ``origin_tracked`` None means unknown."""

        if retention is None:
            return "old_name_view false"
        old: MigrationRelation = migration_relation_for_location(origin)
        reuser: CompiledModel | None = next(
            (
                model
                for model in self._models_by_name.values()
                if migration_relation_for_location(model.destination).matches(old)
            ),
            None,
        )
        if reuser is not None:
            return f"name reused by model:{reuser.name}"
        if any(migration_relation_for_location(view.old).matches(old) for view in self._views):
            return "old name is a compatibility view"
        if origin_tracked is False:
            return "not built by SQLBuild"
        return None

    def _from_history(
        self, *, history: OldNameViewHistory, model: CompiledModel
    ) -> OldNameViewPlanEntry | None:
        """Resume a recorded move; its record proves SQLBuild owned the origin when it moved."""

        status: OldNameViewStatus = history.status(now=self._now)
        action: OldNameViewAction | None = _PENDING_ACTIONS.get(status)
        if action is None:
            return None
        if status in _RESUMED_STATUSES:
            reason: str | None = self._skip_reason(
                origin=_location(runtime=self._runtime, relation=history.old),
                origin_tracked=None,
                retention=resolve_old_name_view_retention(
                    config_values=model.config.values, project_retention=self._project_retention
                ),
            )
            if reason is not None:
                return _skipped_resume(runtime=self._runtime, history=history, reason=reason)
        duration: Duration | None = Duration.parse(history.required.view_retention or "")
        expires_at: datetime | None = (
            history.created.expires_at
            if history.created is not None
            else (None if duration is None else duration.add_to(self._now))
        )
        return OldNameViewPlanEntry(
            model_name=model.name,
            origin=_location(runtime=self._runtime, relation=history.old),
            destination=_location(runtime=self._runtime, relation=history.new),
            action=action,
            target_name=history.move.target_name,
            retention=history.required.view_retention,
            expires_at=expires_at,
            column_aliases=(
                history.created.column_aliases
                if history.created is not None
                else self._planned_aliases(model)
            ),
            stores_history=_stores_history(model),
            migration_event_id=history.move.event_id,
            grants_copied=(
                None
                if history.created is None or history.created.grants_copied is None
                else len(history.created.grants_copied)
            ),
            grants_supported=self._runtime.adapter.relation_grants_supported,
            archived=history.archived is not None,
        )

    def _newest_history(
        self, *, destination: MigrationRelation, origin: MigrationRelation | None
    ) -> OldNameViewHistory | None:
        matching: tuple[OldNameViewHistory, ...] = tuple(
            history
            for history in self._histories
            if history.move.destination.matches(destination)
            and (origin is None or history.move.origin.matches(origin))
        )
        if not matching:
            return None
        return max(matching, key=lambda item: (item.move.created_at, item.move.event_id))

    def _planned_aliases(self, model: CompiledModel) -> tuple[tuple[str, str], ...]:
        if _stores_history(model):
            return tuple(
                sorted(
                    (entry.origin_column, entry.destination_column)
                    for entry in self._column_entries
                    if entry.model_name == model.name and entry.decision in _ALIAS_DECISIONS
                )
            )
        return declared_column_aliases(model)


def declared_column_aliases(model: CompiledModel) -> tuple[tuple[str, str], ...]:
    """Return old-to-new column names a table or view model declares with migrate_from."""

    columns: tuple[SchemaColumn, ...] = (
        model.schema_entry.columns if model.schema_entry is not None else ()
    )
    return tuple(
        sorted(
            (column.migrate_from.strip(), column.name)
            for column in columns
            if column.migrate_from is not None
        )
    )


def _starts_move(entry: ModelMigrationPlanEntry) -> bool:
    if entry.blocks_build:
        return False
    return entry.decision.moves_data or (
        entry.decision == MigrationDecision.RENAMED and entry.completed_at is None
    )


def _skips_pending(entry: OldNameViewPlanEntry) -> bool:
    return entry.action == OldNameViewAction.NONE and entry.migration_event_id is not None


def _skipped_resume(
    *, runtime: PlannerRuntime, history: OldNameViewHistory, reason: str
) -> OldNameViewPlanEntry:
    return OldNameViewPlanEntry(
        model_name=history.move.destination_model,
        origin=_location(runtime=runtime, relation=history.old),
        destination=_location(runtime=runtime, relation=history.new),
        action=OldNameViewAction.NONE,
        target_name=history.move.target_name,
        migration_event_id=history.move.event_id,
        reason=reason,
    )


def _stores_history(model: CompiledModel) -> bool:
    return (
        get_config_str(values=model.config.values, key="materialized") in _HISTORY_MATERIALIZATIONS
    )


def _skipped_entry(*, entry: ModelMigrationPlanEntry, reason: str) -> OldNameViewPlanEntry:
    return OldNameViewPlanEntry(
        model_name=entry.model_name,
        origin=entry.origin,
        destination=entry.destination,
        action=OldNameViewAction.NONE,
        target_name=entry.target_name,
        reason=reason,
    )


def _needed_schemas(
    *,
    runtime: PlannerRuntime,
    selected: tuple[CompiledModel, ...],
    snapshot: WarehouseSnapshot,
    migration_entries: tuple[ModelMigrationPlanEntry, ...],
) -> set[str]:
    """Return schemas whose old-name facts this plan needs."""

    schemas: set[str] = {
        model.destination.schema for model in selected if model.destination.schema is not None
    }
    schemas.update(
        entry.origin.schema for entry in migration_entries if entry.origin.schema is not None
    )
    if runtime.project.unmatched_literal_sql_relations or any(
        _may_claim_view(model=model, snapshot=snapshot) for model in selected
    ):
        schemas.update(project_schemas(runtime=runtime))
    return schemas


def _schemas_to_read(*, snapshot: WarehouseSnapshot, needed: set[str]) -> set[str]:
    """Skip schemas the warehouse snapshot already listed without finding old-name state."""

    listed: frozenset[str] | None = snapshot.listed_state_schemas
    return {
        schema
        for schema in needed
        if schema.lower() in snapshot.old_name_view_state_schemas
        or (listed is not None and schema.lower() not in listed)
    }


def _may_claim_view(*, model: CompiledModel, snapshot: WarehouseSnapshot) -> bool:
    relation: RelationInfo | None = snapshot.existing_relations.get(model.name)
    return relation is not None and _is_view(relation)


def _is_view(relation: RelationInfo) -> bool:
    return normalize_relation_type(relation.relation_type) == RelationType.VIEW


def _claim_errors(
    *,
    selected: Iterable[CompiledModel],
    snapshot: WarehouseSnapshot,
    views: tuple[OldNameView, ...],
    now: datetime,
) -> tuple[PlanWarning, ...]:
    """Refuse a model whose destination is a compatibility view still recorded at that name."""

    errors: list[PlanWarning] = []
    model: CompiledModel
    for model in selected:
        if not _may_claim_view(model=model, snapshot=snapshot):
            continue
        destination: MigrationRelation = migration_relation_for_location(model.destination)
        view: OldNameView | None = next(
            (
                view
                for view in views
                if view.destination_model != model.name
                and migration_relation_for_location(view.old).matches(destination)
            ),
            None,
        )
        if view is not None:
            errors.append(
                PlanWarning(
                    model_name=model.name,
                    severity=WarningSeverity.ERROR,
                    message=claim_message(model_name=model.name, view=view, now=now),
                    code="M114",
                )
            )
    return tuple(errors)


def _old_name_reference_errors(
    *,
    runtime: PlannerRuntime,
    views: tuple[OldNameView, ...],
    entries: tuple[OldNameViewPlanEntry, ...],
) -> tuple[PlanWarning, ...]:
    """Refuse literal Python SQL that reads a name kept only as a compatibility view."""

    literals: tuple[LiteralSqlRelation, ...] = runtime.project.unmatched_literal_sql_relations
    if not literals:
        return ()
    index: ProjectRelationIndex = ProjectRelationIndex(
        relations=tuple(
            dict.fromkeys(
                (
                    *(
                        _old_name_relation(old=view.old, model_name=view.destination_model)
                        for view in views
                    ),
                    *(
                        _old_name_relation(old=entry.origin, model_name=entry.model_name)
                        for entry in entries
                        if entry.runs_steps
                    ),
                )
            )
        )
    )
    errors: list[PlanWarning] = []
    literal: LiteralSqlRelation
    for literal in literals:
        match: ProjectRelation | None = match_project_relation(
            index=index, relation=literal.relation
        )
        if match is None or match.compatibility_for is None:
            continue
        written: str = ".".join(
            part
            for part in (literal.relation.database, literal.relation.schema, literal.relation.name)
            if part
        )
        errors.append(
            PlanWarning(
                model_name=None,
                severity=WarningSeverity.ERROR,
                message=(
                    f"{literal.relative_path}:{literal.line}: "
                    + old_name_reference_message(
                        owner_label=literal.owner_label,
                        written=written,
                        method=literal.method,
                        model_name=match.compatibility_for,
                    )
                    + "; "
                    + hard_coded_relation_remedy(owner_kind=literal.owner_kind, ref=match.ref)
                ),
                code="P008",
            )
        )
    return tuple(errors)


def _old_name_relation(*, old: CompiledRelationLocation, model_name: str) -> ProjectRelation:
    return ProjectRelation(
        ref=SqlResourceRef(kind=SqlResourceRefKind.MODEL, name=model_name),
        relation=RelationName(name=old.name, schema=old.schema, database=old.database),
        compatibility_for=model_name,
    )


def claim_message(*, model_name: str, view: OldNameView, now: datetime) -> str:
    """Describe why a model cannot take a name held by a compatibility view."""

    name: str = view.old.qualified_name or view.old.name
    if view.expires_at is not None and view.expires_at <= now:
        return (
            f"model '{model_name}' would replace {name}, a compatibility view for "
            f"model:{view.destination_model} that expired {view.expires_at:%Y-%m-%d}; run "
            "`sqb janitor` to drop it first"
        )
    until: str = "" if view.expires_at is None else f" until {view.expires_at:%Y-%m-%d}"
    return (
        f"model '{model_name}' would replace {name}, a compatibility view for "
        f"model:{view.destination_model}{until}; drop it early with "
        f"`sqb janitor --drop-old-name-view {name}`"
    )


def _recorded_view(
    *, runtime: PlannerRuntime, history: OldNameViewHistory, models: Iterable[CompiledModel]
) -> OldNameView:
    return OldNameView(
        destination_model=history.move.destination_model,
        old=_location(runtime=runtime, relation=history.old),
        new=_location(runtime=runtime, relation=history.new),
        expires_at=None if history.created is None else history.created.expires_at,
        column_aliases=() if history.created is None else history.created.column_aliases,
        migration_event_id=history.move.event_id,
        target_name=history.move.target_name,
        name_reused_by=next(
            (
                model.name
                for model in models
                if migration_relation_for_location(model.destination).matches(history.old)
            ),
            None,
        ),
    )


def _location(*, runtime: PlannerRuntime, relation: MigrationRelation) -> CompiledRelationLocation:
    return CompiledRelationLocation(
        database=relation.database,
        schema=relation.schema,
        name=relation.name,
        qualified_name=runtime.adapter.render_qualified_name(
            database=relation.database, schema=relation.schema, name=relation.name
        ),
    )
