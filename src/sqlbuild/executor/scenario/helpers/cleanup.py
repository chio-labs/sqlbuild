"""Helpers for targeted scenario cleanup."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledRelationTarget
from sqlbuild.compiler.planner.models import (
    ModelPlanEntry,
    ScenarioExecutionPlan,
    ScenarioFixturePlan,
    SeedPlanEntry,
)
from sqlbuild.compiler.planner.types import MaterializationType, ScenarioArtifactKind
from sqlbuild.executor.scenario.models import ScenarioCleanupTarget
from sqlbuild.shared.helpers.naming import resolve_target_qualified_name


def collect_scenario_cleanup_targets(
    *,
    scenario_plan: ScenarioExecutionPlan,
    adapter: BaseAdapter,
) -> tuple[ScenarioCleanupTarget, ...]:
    """Collect only current-plan scenario relations eligible for cleanup."""

    targets: list[ScenarioCleanupTarget] = []
    seen: set[str] = set()

    fixture_plan: ScenarioFixturePlan
    for fixture_plan in scenario_plan.fixture_plans:
        _append_target(
            targets=targets,
            seen=seen,
            kind=fixture_plan.kind,
            logical_name=fixture_plan.logical_name,
            target=fixture_plan.target,
            adapter=adapter,
        )

    seed_entry: SeedPlanEntry
    for seed_entry in scenario_plan.seed_entries:
        _append_target(
            targets=targets,
            seen=seen,
            kind=ScenarioArtifactKind.SEED,
            logical_name=seed_entry.name,
            target=seed_entry.target,
            adapter=adapter,
        )

    model_entry_map: dict[str, ModelPlanEntry] = {
        entry.name: entry for entry in scenario_plan.model_entries
    }
    model_name: str
    model_target: CompiledRelationTarget
    for model_name, model_target in sorted(scenario_plan.relation_plan.model_targets.items()):
        if model_name in scenario_plan.relation_plan.ref_fixture_targets:
            continue
        model_entry: ModelPlanEntry | None = model_entry_map.get(model_name)
        materialization_type: MaterializationType = MaterializationType.TABLE
        if model_entry is not None:
            materialization_type = model_entry.materialization_type
        _append_target(
            targets=targets,
            seen=seen,
            kind=ScenarioArtifactKind.MODEL,
            logical_name=model_name,
            target=model_target,
            adapter=adapter,
            materialization_type=materialization_type,
        )

    return tuple(targets)


def _append_target(
    *,
    targets: list[ScenarioCleanupTarget],
    seen: set[str],
    kind: ScenarioArtifactKind,
    logical_name: str,
    target: CompiledRelationTarget,
    adapter: BaseAdapter,
    materialization_type: MaterializationType = MaterializationType.TABLE,
) -> None:
    target_relation: str = resolve_target_qualified_name(adapter=adapter, target=target)
    if target_relation in seen:
        return
    seen.add(target_relation)
    targets.append(
        ScenarioCleanupTarget(
            kind=kind,
            logical_name=logical_name,
            target_relation=target_relation,
            materialization_type=materialization_type,
        )
    )
