"""Per-run decisions for in-place column renames of incremental and snapshot models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.compiler.compile.models import CompiledModel, CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.migrations.main._newest_column_event import (
    newest_column_migration_event_mentioning,
)
from sqlbuild.compiler.migrations.main.relation_for_location import migration_relation_for_location
from sqlbuild.compiler.migrations.models import ColumnMigrationEvent
from sqlbuild.compiler.migrations.types import ColumnMigrationDecision, MigrationDiscovery
from sqlbuild.compiler.planner._helpers.identity.hashing import model_definition_hash
from sqlbuild.compiler.planner._helpers.migrations.column_renames import (
    identical_renames,
    rename_hints,
)
from sqlbuild.compiler.planner._helpers.migrations.planning import (
    missing_origin_policy,
    planning_database,
    redirected_cursor_snapshots,
)
from sqlbuild.compiler.planner._helpers.migrations.projections import (
    parse_query_shape,
    renames_explain_change,
)
from sqlbuild.compiler.planner.classes.known_input_columns import KnownInputColumns
from sqlbuild.compiler.planner.classes.migration_state_inspection import (
    MigrationStateInspection,
)
from sqlbuild.compiler.planner.constants import MISSING_ORIGIN_OUTCOMES
from sqlbuild.compiler.planner.models import (
    ColumnMigrationPlanEntry,
    ColumnMigrationPlanning,
    ColumnRenameHint,
    DeferralInputs,
    PlannerOverrides,
    PlannerRuntime,
    PlannerScope,
    PlanWarning,
    QueryShape,
    WarehouseFingerprints,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import InputColumns, MaterializationType, WarningSeverity
from sqlbuild.spec.contracts.main.get_config_str import get_config_str
from sqlbuild.spec.contracts.types import MissingMigrationOriginPolicy

_HISTORY_MATERIALIZATIONS: frozenset[str] = frozenset(
    {MaterializationType.INCREMENTAL, MaterializationType.SNAPSHOT}
)


@dataclass(frozen=True)
class _ModelColumns:
    """Inputs gathered for one model that may rename columns this run."""

    model: CompiledModel
    warehouse: dict[str, ColumnInfo]
    declared: dict[str, str]
    fingerprint: Fingerprint | None
    previous: QueryShape | None
    current: QueryShape | None


@dataclass(frozen=True)
class _Pair:
    """One old-to-new column rename and how it was requested."""

    origin: str
    destination: str
    discovery: MigrationDiscovery


def plan_column_migrations(
    *,
    runtime: PlannerRuntime,
    scope: PlannerScope,
    snapshot: WarehouseSnapshot,
    full_refresh_model_names: frozenset[str],
    physical_relations: Mapping[str, str],
    overrides: PlannerOverrides,
    deferral: DeferralInputs,
    source_columns: Mapping[str, tuple[ColumnInfo, ...]],
) -> ColumnMigrationPlanning:
    """Decide declared and detected column renames and project the renamed snapshot."""

    dialect: str | None = runtime.adapter.sql_analysis_dialect()
    candidates: tuple[_ModelColumns, ...] = tuple(
        candidate
        for key in scope.execution_order
        if (
            candidate := _candidate(
                key=key,
                scope=scope,
                snapshot=snapshot,
                full_refresh_model_names=full_refresh_model_names,
                dialect=dialect,
            )
        )
        is not None
    )
    if not candidates:
        return ColumnMigrationPlanning(snapshot=snapshot)
    state: MigrationStateInspection = MigrationStateInspection(
        adapter=runtime.adapter,
        connection=runtime.connection,
        database=planning_database(runtime=runtime),
    )
    state.inspect_column_events(
        schemas={
            candidate.model.destination.schema
            for candidate in candidates
            if candidate.model.destination.schema is not None
        }
    )
    input_columns: InputColumns = KnownInputColumns(
        model_columns=snapshot.existing_columns,
        source_columns=source_columns,
    )
    entries: list[ColumnMigrationPlanEntry] = []
    hints: list[ColumnRenameHint] = []
    warnings: list[PlanWarning] = []
    candidate: _ModelColumns
    for candidate in candidates:
        model_entries: tuple[ColumnMigrationPlanEntry, ...]
        model_warnings: tuple[PlanWarning, ...]
        model_entries, model_warnings = _checked_entries(
            runtime=runtime,
            candidate=candidate,
            entries=_decide(
                runtime=runtime,
                candidate=candidate,
                events=state.column_events,
                input_columns=input_columns,
            ),
            physical_relation=physical_relations.get(candidate.model.name),
        )
        entries.extend(model_entries)
        warnings.extend(model_warnings)
        hints.extend(_hints(candidate=candidate, entries=model_entries))
    origin_policy: MissingMigrationOriginPolicy = missing_origin_policy(runtime=runtime)
    entries = [replace(entry, missing_origin_policy=origin_policy) for entry in entries]
    warnings.extend(warning for entry in entries if (warning := _entry_warning(entry)))
    overlaid: WarehouseSnapshot = _overlay_snapshot(
        snapshot=snapshot,
        candidates=candidates,
        entries=tuple(entries),
        input_columns=input_columns,
    )
    return ColumnMigrationPlanning(
        snapshot=_with_renamed_cursors(
            runtime=runtime,
            scope=scope,
            snapshot=overlaid,
            entries=tuple(entries),
            physical_relations=physical_relations,
            overrides=overrides,
            deferral=deferral,
        ),
        entries=tuple(entries),
        hints=tuple(hints),
        warnings=tuple(warnings),
    )


def _candidate(
    *,
    key: CompiledObjectKey,
    scope: PlannerScope,
    snapshot: WarehouseSnapshot,
    full_refresh_model_names: frozenset[str],
    dialect: str | None,
) -> _ModelColumns | None:
    if key not in scope.selected_keys or key.resource_type != CompiledResourceType.MODEL:
        return None
    model: CompiledModel | None = scope.models_by_name.get(key.name)
    if (
        model is None
        or get_config_str(values=model.config.values, key="materialized")
        not in _HISTORY_MATERIALIZATIONS
        or model.name in full_refresh_model_names
        or model.name not in snapshot.existing_relations
    ):
        return None
    warehouse: tuple[ColumnInfo, ...] = snapshot.existing_columns.get(model.name, ())
    declared: dict[str, str] = {
        column.name: column.migrate_from.strip()
        for column in (model.schema_entry.columns if model.schema_entry is not None else ())
        if column.migrate_from is not None
    }
    fingerprint: Fingerprint | None = snapshot.fingerprints.models.get(model.name)
    changed: bool = (
        fingerprint is not None
        and fingerprint.definition_hash
        != model_definition_hash(
            model_name=model.name, query_sql=model.query_sql, dialect=snapshot.column_dialect
        )
    )
    if not warehouse or (not declared and not changed):
        return None
    return _ModelColumns(
        model=model,
        warehouse={column.name.lower(): column for column in warehouse},
        declared=declared,
        fingerprint=fingerprint,
        previous=(
            parse_query_shape(query_sql=fingerprint.definition, dialect=dialect)
            if changed and fingerprint is not None
            else None
        ),
        current=parse_query_shape(query_sql=model.query_sql, dialect=dialect),
    )


def _decide(
    *,
    runtime: PlannerRuntime,
    candidate: _ModelColumns,
    events: tuple[ColumnMigrationEvent, ...],
    input_columns: InputColumns,
) -> tuple[ColumnMigrationPlanEntry, ...]:
    entries: list[ColumnMigrationPlanEntry] = []
    pair: _Pair
    for pair in (
        *_declared_pairs(candidate),
        *_detected_pairs(candidate=candidate, input_columns=input_columns),
    ):
        entry: ColumnMigrationPlanEntry | None = _decide_pair(
            runtime=runtime, candidate=candidate, pair=pair, events=events
        )
        if entry is not None:
            entries.append(entry)
    return tuple(entries)


def _declared_pairs(candidate: _ModelColumns) -> tuple[_Pair, ...]:
    return tuple(
        _Pair(origin=origin, destination=destination, discovery=MigrationDiscovery.MANUAL)
        for destination, origin in candidate.declared.items()
    )


def _detected_pairs(*, candidate: _ModelColumns, input_columns: InputColumns) -> tuple[_Pair, ...]:
    if candidate.previous is None or candidate.current is None:
        return ()
    declared: dict[str, str] = {
        origin: destination for destination, origin in candidate.declared.items()
    }
    return tuple(
        _Pair(origin=origin, destination=destination, discovery=MigrationDiscovery.AUTOMATIC)
        for origin, destination in identical_renames(
            previous=candidate.previous,
            current=candidate.current,
            excluded=_declared_names(candidate),
            declared=declared,
            input_columns=input_columns,
        )
    )


def _declared_names(candidate: _ModelColumns) -> frozenset[str]:
    return frozenset(
        {name.lower() for name in candidate.declared}
        | {origin.lower() for origin in candidate.declared.values()}
    )


def _decide_pair(
    *,
    runtime: PlannerRuntime,
    candidate: _ModelColumns,
    pair: _Pair,
    events: tuple[ColumnMigrationEvent, ...],
) -> ColumnMigrationPlanEntry | None:
    """Decide one rename from live columns first, then from recorded events."""

    origin: ColumnInfo | None = candidate.warehouse.get(pair.origin.lower())
    has_destination: bool = pair.destination.lower() in candidate.warehouse
    newest: ColumnMigrationEvent | None = newest_column_migration_event_mentioning(
        events=events,
        relation=migration_relation_for_location(candidate.model.destination),
        origin_column=pair.origin,
        destination_column=pair.destination,
    )
    recorded: bool = newest is not None and newest.renamed(
        origin_column=pair.origin, destination_column=pair.destination
    )
    decision: ColumnMigrationDecision
    if recorded and (has_destination or origin is None):
        decision = ColumnMigrationDecision.DONE
    elif pair.origin.lower() in _output_names(candidate):
        decision = ColumnMigrationDecision.STILL_PRODUCED
    elif origin is not None and not has_destination:
        decision = ColumnMigrationDecision.RENAME
    elif origin is None and has_destination:
        decision = ColumnMigrationDecision.RECORD
    elif origin is not None:
        decision = ColumnMigrationDecision.CONFLICT
    else:
        decision = ColumnMigrationDecision.SOURCE_MISSING
    if pair.discovery == MigrationDiscovery.AUTOMATIC and decision.blocks_build:
        return None
    return ColumnMigrationPlanEntry(
        model_name=candidate.model.name,
        destination=candidate.model.destination,
        origin_column=origin.name if origin is not None else pair.origin,
        destination_column=pair.destination,
        discovery=pair.discovery,
        decision=decision,
        target_name=(
            newest.target_name
            if decision == ColumnMigrationDecision.DONE and newest is not None
            else runtime.project.effective_target_name
        ),
        completed_at=(
            newest.created_at
            if decision == ColumnMigrationDecision.DONE and newest is not None
            else None
        ),
    )


def _output_names(candidate: _ModelColumns) -> frozenset[str]:
    if candidate.current is not None:
        return frozenset(projection.key for projection in candidate.current.projections)
    return frozenset(column.name.lower() for column in candidate.model.inferred_columns or ())


def _checked_entries(
    *,
    runtime: PlannerRuntime,
    candidate: _ModelColumns,
    entries: tuple[ColumnMigrationPlanEntry, ...],
    physical_relation: str | None,
) -> tuple[tuple[ColumnMigrationPlanEntry, ...], tuple[PlanWarning, ...]]:
    """Ask the adapter once per model whether pending renames can run in place."""

    if not any(entry.decision.renames for entry in entries):
        return entries, ()
    relation: str = (
        physical_relation
        or candidate.model.destination.qualified_name
        or candidate.model.destination.name
    )
    reason: str | None = runtime.adapter.column_rename_unavailable_reason(
        connection=runtime.connection, destination=relation
    )
    if reason is None:
        return entries, ()
    checked: list[ColumnMigrationPlanEntry] = []
    warnings: list[PlanWarning] = []
    entry: ColumnMigrationPlanEntry
    for entry in entries:
        if not entry.decision.renames:
            checked.append(entry)
        elif entry.discovery == MigrationDiscovery.MANUAL:
            checked.append(
                replace(entry, decision=ColumnMigrationDecision.UNSUPPORTED, message=reason)
            )
        else:
            warnings.append(
                PlanWarning(
                    model_name=entry.model_name,
                    severity=WarningSeverity.WARNING,
                    message=(
                        f"column {entry.destination_column} looks renamed from "
                        f"{entry.origin_column}, but it cannot be renamed in place: {reason}; "
                        "the change follows on_schema_change instead"
                    ),
                    code="M112",
                )
            )
    return tuple(checked), tuple(warnings)


def _hints(
    *, candidate: _ModelColumns, entries: tuple[ColumnMigrationPlanEntry, ...]
) -> tuple[ColumnRenameHint, ...]:
    if candidate.previous is None or candidate.current is None:
        return ()
    claimed: frozenset[str] = frozenset(
        {entry.origin_column.lower() for entry in entries}
        | {entry.destination_column.lower() for entry in entries}
    )
    return rename_hints(
        model_name=candidate.model.name,
        previous=candidate.previous,
        current=candidate.current,
        excluded=_declared_names(candidate) | claimed,
        live_columns=frozenset(candidate.warehouse),
    )


def _overlay_snapshot(
    *,
    snapshot: WarehouseSnapshot,
    candidates: tuple[_ModelColumns, ...],
    entries: tuple[ColumnMigrationPlanEntry, ...],
    input_columns: InputColumns,
) -> WarehouseSnapshot:
    """Plan each model as if its columns were already renamed and its query unchanged."""

    if not entries:
        return snapshot
    blocked: frozenset[str] = frozenset(
        entry.model_name for entry in entries if entry.blocks_build or entry.origin_missing
    )
    columns: dict[str, tuple[ColumnInfo, ...]] = dict(snapshot.existing_columns)
    fingerprints: dict[str, Fingerprint] = dict(snapshot.fingerprints.models)
    candidate: _ModelColumns
    for candidate in candidates:
        renames: dict[str, str] = {
            entry.origin_column: entry.destination_column
            for entry in entries
            if entry.model_name == candidate.model.name
        }
        if not renames or candidate.model.name in blocked:
            continue
        pending: dict[str, str] = {
            entry.origin_column.lower(): entry.destination_column
            for entry in entries
            if entry.model_name == candidate.model.name and entry.decision.renames
        }
        columns[candidate.model.name] = tuple(
            replace(column, name=pending.get(column.name.lower(), column.name))
            for column in snapshot.existing_columns.get(candidate.model.name, ())
        )
        if (
            candidate.fingerprint is not None
            and candidate.previous is not None
            and candidate.current is not None
            and renames_explain_change(
                previous=candidate.previous,
                current=candidate.current,
                renames=renames,
                input_columns=input_columns,
            )
        ):
            fingerprints[candidate.model.name] = replace(
                candidate.fingerprint,
                definition=candidate.model.query_sql,
                definition_hash=model_definition_hash(
                    model_name=candidate.model.name,
                    query_sql=candidate.model.query_sql,
                    dialect=snapshot.column_dialect,
                ),
            )
    return replace(
        snapshot,
        existing_columns=columns,
        fingerprints=WarehouseFingerprints(
            models=fingerprints,
            functions=snapshot.fingerprints.functions,
            seeds=snapshot.fingerprints.seeds,
            python_nodes=snapshot.fingerprints.python_nodes,
        ),
    )


def _with_renamed_cursors(
    *,
    runtime: PlannerRuntime,
    scope: PlannerScope,
    snapshot: WarehouseSnapshot,
    entries: tuple[ColumnMigrationPlanEntry, ...],
    physical_relations: Mapping[str, str],
    overrides: PlannerOverrides,
    deferral: DeferralInputs,
) -> WarehouseSnapshot:
    """Read the target watermark from the old column when the cursor column is renamed."""

    old_cursor_columns: dict[str, str] = {}
    entry: ColumnMigrationPlanEntry
    for entry in entries:
        model: CompiledModel | None = scope.models_by_name.get(entry.model_name)
        cursor: str | None = (
            get_config_str(values=model.config.values, key="cursor") if model else None
        )
        if (
            entry.decision.renames
            and cursor is not None
            and cursor.lower() == entry.destination_column.lower()
        ):
            old_cursor_columns[entry.model_name] = entry.origin_column
    if not old_cursor_columns:
        return snapshot
    return replace(
        snapshot,
        cursor_snapshots={
            **snapshot.cursor_snapshots,
            **redirected_cursor_snapshots(
                runtime=runtime,
                scope=scope,
                existing_relations=snapshot.existing_relations,
                target_relations={
                    name: physical_relations.get(name)
                    or scope.models_by_name[name].destination.qualified_name
                    or name
                    for name in old_cursor_columns
                },
                overrides=overrides,
                deferral=deferral,
                origin_cursor_columns=old_cursor_columns,
            ),
        },
    )


def _entry_warning(entry: ColumnMigrationPlanEntry) -> PlanWarning | None:
    relation: str = entry.destination.qualified_name or entry.destination.name
    declaration: str = f"column '{entry.destination_column}' migrate_from {entry.origin_column}"
    if entry.decision == ColumnMigrationDecision.DONE:
        if entry.discovery != MigrationDiscovery.MANUAL:
            return None
        completed: str = entry.completed_at.isoformat() if entry.completed_at else "unknown time"
        return PlanWarning(
            model_name=entry.model_name,
            severity=WarningSeverity.WARNING,
            message=(
                f"column rename {entry.origin_column} -> {entry.destination_column} on "
                f"{relation} completed at {completed} on target "
                f"'{entry.target_name or 'default'}'; "
                f"migrate_from can be removed from column '{entry.destination_column}' of "
                f"'{entry.model_name}'"
            ),
            code="M108",
        )
    messages: dict[ColumnMigrationDecision, tuple[str, str]] = {
        ColumnMigrationDecision.SOURCE_MISSING: (
            "M109",
            f"model '{entry.model_name}': {declaration}: column {entry.origin_column} does not "
            f"exist in {relation} and no recorded rename into {entry.destination_column} was "
            f"found; {MISSING_ORIGIN_OUTCOMES[entry.missing_origin_policy]}",
        ),
        ColumnMigrationDecision.CONFLICT: (
            "M110",
            f"model '{entry.model_name}': {declaration}: {relation} already has both "
            f"{entry.origin_column} and {entry.destination_column}, so the column cannot be "
            "renamed in place; drop one of them, or remove migrate_from and let "
            "on_schema_change handle the columns",
        ),
        ColumnMigrationDecision.STILL_PRODUCED: (
            "M111",
            f"model '{entry.model_name}': {declaration}: the model still produces "
            f"{entry.origin_column}; remove it from the query, or remove migrate_from",
        ),
        ColumnMigrationDecision.UNSUPPORTED: (
            "M112",
            f"model '{entry.model_name}': {declaration}: {entry.message}",
        ),
    }
    coded: tuple[str, str] | None = messages.get(entry.decision)
    if coded is None:
        return None
    return PlanWarning(
        model_name=entry.model_name,
        severity=WarningSeverity.ERROR if entry.blocks_build else WarningSeverity.WARNING,
        message=coded[1],
        code=coded[0],
    )
