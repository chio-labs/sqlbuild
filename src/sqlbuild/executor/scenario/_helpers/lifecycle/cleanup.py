"""Helpers for targeted scenario cleanup."""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from dataclasses import replace
from typing import Any

from sqlbuild._native import (
    CompiledRelationLocation,
    MaterializationType,
    ModelPlanEntry,
    ScenarioArtifactKind,
    ScenarioExecutionPlan,
    ScenarioFixturePlan,
    SeedPlanEntry,
)
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationInfo, RelationLookup
from sqlbuild.adapter.contract.types import RelationType
from sqlbuild.adapter.relations.main.resolve_qualified_name_parts import (
    resolve_qualified_name_parts,
)
from sqlbuild.adapter.relations.main.resolve_relation_location_qualified_name import (
    resolve_relation_location_qualified_name,
)
from sqlbuild.adapter.type_system.main.normalize_relation_type import normalize_relation_type
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event
from sqlbuild.executor.run.main._table_targets import resolve_table_targets
from sqlbuild.executor.run.main._type_enforcement_relation_name import (
    resolve_type_enforcement_relation_name,
)
from sqlbuild.executor.run.models import TableTargets
from sqlbuild.executor.scenario.models import ScenarioCleanupTarget

_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.execution")

_MINIMUM_LISTING_PREFIX: int = 8


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
            enforced_table: str = resolve_type_enforcement_relation_name(
                adapter=adapter, staging_table=table_targets.staging_table
            )
            candidates.append(
                ScenarioCleanupTarget(
                    kind=ScenarioArtifactKind.MODEL,
                    logical_name=model_name,
                    target_relation=resolve_qualified_name_parts(
                        adapter=adapter,
                        database=table_targets.target_database,
                        schema=table_targets.target_schema,
                        name=enforced_table,
                    ),
                    database=table_targets.target_database,
                    schema=table_targets.target_schema,
                    name=enforced_table,
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
    """Return targets to drop: catalogued ones typed by the catalog, plus every unlistable one."""

    listed_targets: tuple[ScenarioCleanupTarget, ...] = tuple(
        target for target in targets if _authoritatively_listable(target=target, adapter=adapter)
    )
    names_by_database: defaultdict[str | None, set[str]] = defaultdict(set)
    schemas_by_database: defaultdict[str | None, set[str]] = defaultdict(set)
    target: ScenarioCleanupTarget
    for target in listed_targets:
        names_by_database[target.database].update(_case_variants(str(target.name)))
        schemas_by_database[target.database].update(_case_variants(str(target.schema)))
    exact_types: dict[tuple[str | None, str | None, str], str] = {}
    folded_types: dict[tuple[str | None, str | None, str], str] = {}
    try:
        database: str | None
        names: set[str]
        for database, names in names_by_database.items():
            database_targets: tuple[ScenarioCleanupTarget, ...] = tuple(
                target for target in listed_targets if target.database == database
            )
            prefix: str = os.path.commonprefix(
                [str(target.name).lower() for target in database_targets]
            )
            relations: tuple[RelationInfo, ...] | None = (
                adapter.list_relations_with_prefix(
                    connection=connection,
                    database=database,
                    schemas=tuple(sorted({str(target.schema) for target in database_targets})),
                    prefix=prefix,
                )
                if len(prefix) >= _MINIMUM_LISTING_PREFIX
                else None
            )
            relation: RelationInfo
            for relation in (
                relations
                if relations is not None
                else adapter.list_relations(
                    connection=connection,
                    database=database,
                    schemas=tuple(sorted(schemas_by_database[database])),
                    names=tuple(sorted(names)),
                )
            ):
                exact_types[(database, relation.schema, relation.name)] = relation.relation_type
                folded_types[
                    RelationLookup.key(
                        database=database, schema=relation.schema, name=relation.name
                    )
                ] = relation.relation_type
    except Exception as exc:
        log_debug_event(
            logger=_DEBUG_LOGGER,
            message="scenario cleanup catalog read failed; dropping every target",
            sqlbuild_error=str(exc),
        )
        return targets
    existing: list[ScenarioCleanupTarget] = []
    for target in targets:
        if target not in listed_targets:
            existing.append(target)
            continue
        relation_type: str | None = exact_types.get(
            (target.database, target.schema, str(target.name))
        ) or folded_types.get(
            RelationLookup.key(
                database=target.database, schema=target.schema, name=str(target.name)
            )
        )
        if relation_type is None:
            continue
        listed_type: RelationType = normalize_relation_type(relation_type)
        existing.append(
            replace(
                target,
                materialization_type=(
                    MaterializationType.VIEW
                    if listed_type == RelationType.VIEW
                    else MaterializationType.TABLE
                ),
                listed=listed_type != RelationType.OTHER,
            )
        )
    return tuple(existing)


def confirmed_absent_targets(
    *,
    targets: tuple[ScenarioCleanupTarget, ...],
    dropped: tuple[ScenarioCleanupTarget, ...],
    adapter: BaseAdapter,
) -> tuple[tuple[str | None, str | None, str], ...]:
    """Locations a successful cleanup left empty: listed absent, or dropped by their listed kind."""

    unconfirmed: set[str] = {target.target_relation for target in dropped if not target.listed}
    return tuple(
        (target.database, target.schema, str(target.name))
        for target in targets
        if _authoritatively_listable(target=target, adapter=adapter)
        and target.target_relation not in unconfirmed
    )


def _authoritatively_listable(*, target: ScenarioCleanupTarget, adapter: BaseAdapter) -> bool:
    return (
        target.name is not None
        and target.schema is not None
        and adapter.lists_relations_authoritatively(database=target.database, schema=target.schema)
    )


def _case_variants(value: str) -> tuple[str, ...]:
    return (value, value.lower(), value.upper())
