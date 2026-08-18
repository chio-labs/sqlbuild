"""Standard planner source freshness orchestration helpers."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import (
    PlannerRelationsContext,
    PlannerScope,
)
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
                state_schema: state_schema.lower() in freshness_state_schemas
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


def _resolve_state_database(project: CompiledProject) -> str | None:
    model_destination: CompiledRelationLocation
    for model_destination in _iter_state_destinations(project=project):
        if model_destination.database is not None:
            return model_destination.database
    return None


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
