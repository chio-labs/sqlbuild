"""Helpers for targeted scenario cleanup."""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import replace
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationInfo, RelationLookup
from sqlbuild.adapter.contract.types import RelationType
from sqlbuild.adapter.relations.main.resolve_relation_location_qualified_name import (
    resolve_relation_location_qualified_name,
)
from sqlbuild.adapter.type_system.main.normalize_relation_type import normalize_relation_type
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.planner.models import (
    ModelPlanEntry,
    ScenarioExecutionPlan,
    ScenarioFixturePlan,
    SeedPlanEntry,
)
from sqlbuild.compiler.planner.types import MaterializationType, ScenarioArtifactKind
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event
from sqlbuild.executor.run.main._table_targets import resolve_table_targets
from sqlbuild.executor.run.models import TableTargets
from sqlbuild.executor.scenario.models import ScenarioCleanupTarget

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.execution")


def collect_scenario_cleanup_targets(
    *,
    scenario_plan: ScenarioExecutionPlan,
    adapter: BaseAdapter,
) -> tuple[ScenarioCleanupTarget, ...]:
    """Collect only current-plan scenario relations eligible for cleanup."""

    candidates: list[ScenarioCleanupTarget] = []

    fixture_plan: ScenarioFixturePlan
    for fixture_plan in scenario_plan.fixture_plans:
        candidates.append(
            _cleanup_target(
                kind=fixture_plan.kind,
                logical_name=fixture_plan.logical_name,
                target=fixture_plan.destination,
                adapter=adapter,
            )
        )

    seed_entry: SeedPlanEntry
    for seed_entry in scenario_plan.seed_entries:
        candidates.append(
            _cleanup_target(
                kind=ScenarioArtifactKind.SEED,
                logical_name=seed_entry.name,
                target=seed_entry.destination,
                adapter=adapter,
            )
        )

    model_entry_map: dict[str, ModelPlanEntry] = {
        entry.name: entry for entry in scenario_plan.model_entries
    }
    model_name: str
    model_target: CompiledRelationLocation
    for model_name, model_target in sorted(scenario_plan.relation_plan.model_locations.items()):
        if model_name in scenario_plan.relation_plan.ref_fixture_locations:
            continue
        model_entry: ModelPlanEntry | None = model_entry_map.get(model_name)
        materialization_type: MaterializationType = MaterializationType.TABLE
        if model_entry is not None:
            materialization_type = model_entry.materialization_type
        candidates.append(
            _cleanup_target(
                kind=ScenarioArtifactKind.MODEL,
                logical_name=model_name,
                target=model_target,
                adapter=adapter,
                materialization_type=materialization_type,
            )
        )
        if model_entry is not None and MaterializationType.is_table_backed(
            materialized=materialization_type
        ):
            table_targets: TableTargets = resolve_table_targets(adapter=adapter, entry=model_entry)
            candidates.append(
                ScenarioCleanupTarget(
                    kind=ScenarioArtifactKind.MODEL,
                    logical_name=model_name,
                    target_relation=table_targets.staging_qualified,
                    database=table_targets.target_database,
                    schema=table_targets.target_schema,
                    name=table_targets.staging_table,
                )
            )

    targets: list[ScenarioCleanupTarget] = []
    seen: set[str] = set()
    candidate: ScenarioCleanupTarget
    for candidate in candidates:
        if candidate.target_relation in seen:
            continue
        seen.add(candidate.target_relation)
        targets.append(candidate)
    return tuple(targets)


def _cleanup_target(
    *,
    kind: ScenarioArtifactKind,
    logical_name: str,
    target: CompiledRelationLocation,
    adapter: BaseAdapter,
    materialization_type: MaterializationType = MaterializationType.TABLE,
) -> ScenarioCleanupTarget:
    target_relation: str = resolve_relation_location_qualified_name(
        adapter=adapter, location=target
    )
    return ScenarioCleanupTarget(
        kind=kind,
        logical_name=logical_name,
        target_relation=target_relation,
        materialization_type=materialization_type,
        database=target.database,
        schema=target.schema,
        name=target.name,
    )


def existing_scenario_cleanup_targets(
    *,
    targets: tuple[ScenarioCleanupTarget, ...],
    adapter: BaseAdapter,
    connection: Any,
) -> tuple[ScenarioCleanupTarget, ...]:
    """Return existing targets typed by the catalog, or every target when it cannot be read."""

    names_by_database: defaultdict[str | None, set[str]] = defaultdict(set)
    schemas_by_database: defaultdict[str | None, set[str]] = defaultdict(set)
    target: ScenarioCleanupTarget
    for target in targets:
        if target.name is None:
            continue
        names_by_database[target.database].update((target.name, target.name.lower()))
        if target.schema is not None:
            schemas_by_database[target.database].add(target.schema)
    existing_types: dict[tuple[str | None, str | None, str], str] = {}
    try:
        database: str | None
        names: set[str]
        for database, names in names_by_database.items():
            schemas: set[str] = schemas_by_database[database]
            relation: RelationInfo
            for relation in adapter.list_relations(
                connection=connection,
                database=database,
                schemas=tuple(sorted(schemas)) if schemas else None,
                names=tuple(sorted(names)),
            ):
                existing_types[
                    _lookup_key(database=database, schema=relation.schema, name=relation.name)
                ] = relation.relation_type
                existing_types[_lookup_key(database=database, schema=None, name=relation.name)] = (
                    relation.relation_type
                )
    except Exception as exc:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="scenario cleanup catalog read failed; dropping every target",
            sqlbuild_error=str(exc),
        )
        return targets
    existing: list[ScenarioCleanupTarget] = []
    for target in targets:
        if target.name is None:
            existing.append(target)
            continue
        relation_type: str | None = existing_types.get(
            _lookup_key(database=target.database, schema=target.schema, name=target.name)
        )
        if relation_type is None:
            continue
        existing.append(
            replace(
                target,
                materialization_type=(
                    MaterializationType.VIEW
                    if normalize_relation_type(relation_type) == RelationType.VIEW
                    else MaterializationType.TABLE
                ),
            )
        )
    return tuple(existing)


def _lookup_key(
    *, database: str | None, schema: str | None, name: str
) -> tuple[str | None, str | None, str]:
    return RelationLookup.key(database=database, schema=schema, name=name)
