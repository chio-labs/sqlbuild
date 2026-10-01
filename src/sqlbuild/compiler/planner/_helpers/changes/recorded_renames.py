"""Collect the model renames that downstream references may have been rewritten for."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner._helpers.identity.hashing import model_definition_hash
from sqlbuild.compiler.planner.classes.migration_state_inspection import (
    MigrationStateInspection,
)
from sqlbuild.compiler.planner.models import (
    PlannerRuntime,
    PlannerScope,
    ReferenceRename,
    WarehouseSnapshot,
)
from sqlbuild.compiler.references.types import SqlReferenceKind


def plan_reference_renames(
    *,
    runtime: PlannerRuntime,
    scope: PlannerScope,
    snapshot: WarehouseSnapshot,
    state: MigrationStateInspection,
    schemas: set[str],
    planned: dict[str, str],
) -> tuple[ReferenceRename, ...]:
    """Return this plan's renames plus recorded renames, read only when a query changed."""

    if not _has_changed_referencing_query(scope=scope, snapshot=snapshot):
        return ()
    state.inspect_migration_events(
        schemas={schema for schema in schemas if schema.lower() in snapshot.migration_state_schemas}
    )
    target_name: str | None = runtime.project.effective_target_name
    return (
        *(
            ReferenceRename(new_name=new_name, origin_name=origin_name)
            for new_name, origin_name in planned.items()
            if new_name != origin_name
        ),
        *(
            ReferenceRename(
                new_name=event.destination_model,
                origin_name=event.origin_model,
                recorded_at=event.created_at,
            )
            for event in state.events
            if event.target_name in (None, target_name)
            and event.origin_model is not None
            and event.origin_model != event.destination_model
        ),
    )


def _has_changed_referencing_query(*, scope: PlannerScope, snapshot: WarehouseSnapshot) -> bool:
    selected: tuple[CompiledModel, ...] = tuple(
        model
        for key in scope.selected_keys
        if (model := scope.models_by_name.get(key.name)) is not None
    )
    return any(_referencing_query_changed(model=model, snapshot=snapshot) for model in selected)


def _referencing_query_changed(*, model: CompiledModel, snapshot: WarehouseSnapshot) -> bool:
    recorded: Fingerprint | None = snapshot.fingerprints.models.get(model.name)
    return (
        recorded is not None
        and any(reference.ref_kind == SqlReferenceKind.REF for reference in model.references)
        and model_definition_hash(
            model_name=model.name, query_sql=model.query_sql, dialect=snapshot.column_dialect
        )
        != recorded.definition_hash
    )
