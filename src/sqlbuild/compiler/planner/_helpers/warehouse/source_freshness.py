"""Standard planner source freshness orchestration helpers."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationLookup
from sqlbuild.adapter.relations.main.relation_lookup import build_relation_lookup
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import (
    PlannerRelationsContext,
    PlannerScope,
    StandardReuseFromTargetModelSnapshot,
    StandardReuseFromTargetSnapshot,
)
from sqlbuild.compiler.source_freshness.constants import SOURCE_FRESHNESS_TABLE_NAME
from sqlbuild.compiler.source_freshness.main._planning import (
    build_standard_source_freshness_planning_result,
)
from sqlbuild.compiler.source_freshness.main._propagation import (
    build_standard_source_freshness_propagation_result,
)
from sqlbuild.compiler.source_freshness.models import StandardSourceFreshnessPlanningResult


def build_planner_source_freshness_result(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    scope: PlannerScope,
    relations: PlannerRelationsContext,
    freshness_state_schemas: frozenset[str] = frozenset(),
) -> StandardSourceFreshnessPlanningResult:
    """Build standard source freshness comparison data for planner output."""

    state_schemas: tuple[str, ...] = _collect_state_schemas(project=project, scope=scope)
    source_freshness: StandardSourceFreshnessPlanningResult = (
        build_standard_source_freshness_planning_result(
            adapter=adapter,
            connection=connection,
            sources=tuple(relations.source_read_map.values()),
            state_database=_resolve_state_database(project),
            state_schemas=state_schemas,
            observed_at=datetime.now(UTC),
            run_id="planning",
            render_qualified_name=adapter.render_qualified_name,
            state_table_exists_by_schema={
                state_schema: state_schema in freshness_state_schemas
                for state_schema in state_schemas
            },
        )
    )
    return replace(
        source_freshness,
        propagation=build_standard_source_freshness_propagation_result(
            source_freshness=source_freshness,
            scope=scope,
        ),
    )


def build_reuse_from_source_freshness_result(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    scope: PlannerScope,
    relations: PlannerRelationsContext,
    reuse_from_snapshot: StandardReuseFromTargetSnapshot,
) -> StandardSourceFreshnessPlanningResult:
    """Compare current source freshness against reuse_from target state."""

    state_database: str | None = _resolve_reuse_origin_state_database(reuse_from_snapshot)
    state_schemas: tuple[str, ...] = _collect_reuse_origin_state_schemas(reuse_from_snapshot)
    state_table_lookup: RelationLookup = build_relation_lookup(
        adapter=adapter,
        connection=connection,
        locations=tuple(
            (state_database, schema, SOURCE_FRESHNESS_TABLE_NAME) for schema in state_schemas
        ),
    )
    source_freshness: StandardSourceFreshnessPlanningResult = (
        build_standard_source_freshness_planning_result(
            adapter=adapter,
            connection=connection,
            sources=tuple(relations.source_read_map.values()),
            state_database=state_database,
            state_schemas=state_schemas,
            observed_at=datetime.now(UTC),
            run_id="planning",
            render_qualified_name=adapter.render_qualified_name,
            state_table_exists_by_schema={
                schema: state_table_lookup.exists(
                    database=state_database,
                    schema=schema,
                    name=SOURCE_FRESHNESS_TABLE_NAME,
                )
                for schema in state_schemas
            },
        )
    )
    return replace(
        source_freshness,
        propagation=build_standard_source_freshness_propagation_result(
            source_freshness=source_freshness,
            scope=scope,
        ),
    )


def _resolve_state_database(project: CompiledProject) -> str | None:
    model_destination: CompiledRelationLocation
    for model_destination in _iter_state_destinations(project=project):
        if model_destination.database is not None:
            return model_destination.database
    return None


def _resolve_reuse_origin_state_database(
    reuse_from_snapshot: StandardReuseFromTargetSnapshot,
) -> str | None:
    model_snapshot: StandardReuseFromTargetModelSnapshot | None = next(
        iter(reuse_from_snapshot.model_snapshots.values()), None
    )
    if model_snapshot is None:
        return None
    return model_snapshot.reuse_origin_fingerprint_database


def _collect_reuse_origin_state_schemas(
    reuse_from_snapshot: StandardReuseFromTargetSnapshot,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                model_snapshot.reuse_origin_fingerprint_schema
                for model_snapshot in reuse_from_snapshot.model_snapshots.values()
            }
        )
    )


def _collect_state_schemas(*, project: CompiledProject, scope: PlannerScope) -> tuple[str, ...]:
    selected_model_names: frozenset[str] = frozenset(
        key.name for key in scope.selected_keys if key.resource_type == CompiledResourceType.MODEL
    )
    schemas: set[str] = set()
    model_destination: CompiledRelationLocation
    for model_destination in _iter_state_destinations(project=project):
        if model_destination.schema is not None:
            schemas.add(model_destination.schema)
    if not schemas:
        model_name: str
        for model_name in selected_model_names:
            model: CompiledModel | None = scope.models_by_name.get(model_name)
            if model is not None and model.destination.schema is not None:
                schemas.add(model.destination.schema)
    return tuple(sorted(schemas))


def _iter_state_destinations(*, project: CompiledProject) -> tuple[CompiledRelationLocation, ...]:
    return (
        *(model.destination for model in project.models),
        *(seed.destination for seed in project.seeds),
        *(function.destination for function in project.functions),
    )
