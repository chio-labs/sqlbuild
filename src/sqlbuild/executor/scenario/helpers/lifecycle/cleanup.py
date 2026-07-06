"""Helpers for targeted scenario cleanup."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledRelationLocation
from sqlbuild.compiler.planner.models import (
    ModelPlanEntry,
    ScenarioExecutionPlan,
    ScenarioFixturePlan,
    SeedPlanEntry,
)
from sqlbuild.compiler.planner.types import MaterializationType, ScenarioArtifactKind
from sqlbuild.executor.scenario.models import ScenarioCleanupTarget
from sqlbuild.shared.helpers.identity.naming import resolve_relation_location_qualified_name


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
    )
