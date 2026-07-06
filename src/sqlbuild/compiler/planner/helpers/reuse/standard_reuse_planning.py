"""Standard target reuse planner orchestration helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.helpers.reuse.standard_reuse_decisions import (
    build_standard_reuse_decisions,
)
from sqlbuild.compiler.planner.helpers.reuse.standard_reuse_from_target import (
    build_standard_reuse_from_target_snapshot,
)
from sqlbuild.compiler.planner.helpers.warehouse.source_freshness import (
    build_reuse_from_source_freshness_result,
)
from sqlbuild.compiler.planner.models import (
    DependencyBaselinePlanEntry,
    ExistingDestinationInputPlanEntry,
    ModelCursorSnapshot,
    ModelPlanEntry,
    PlannerRelationsContext,
    PlannerScope,
    RelationReusePlan,
    StandardReuseFromTargetSnapshot,
    StandardReuseIdentityInputs,
    StandardReusePlanningResult,
)
from sqlbuild.compiler.source_freshness.models import StandardSourceFreshnessPlanningResult
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig


def build_standard_reuse_planning_result(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    scope: PlannerScope,
    relations: PlannerRelationsContext,
    project_config: ProjectConfig | None,
    local_config: LocalConfig | None,
    identity_inputs: StandardReuseIdentityInputs,
    full_refresh: bool,
) -> StandardReusePlanningResult | None:
    """Build snapshot, freshness, and decisions for standard target reuse."""

    if full_refresh:
        return None
    expected_version_hashes: dict[str, str] = identity_inputs.expected_version_hashes
    built_fingerprints: dict[str, Fingerprint] = identity_inputs.built_fingerprints
    destination_relation_names: frozenset[str] = identity_inputs.destination_relation_names
    cursor_snapshots: dict[str, ModelCursorSnapshot] = identity_inputs.cursor_snapshots
    custom_prepare_version_materializations: frozenset[str] = (
        identity_inputs.custom_prepare_version_materializations
    )
    snapshot: StandardReuseFromTargetSnapshot | None = build_standard_reuse_from_target_snapshot(
        project=project,
        adapter=adapter,
        connection=connection,
        scope=scope,
        project_config=project_config,
        local_config=local_config,
    )
    if snapshot is None:
        return None
    source_freshness: StandardSourceFreshnessPlanningResult | None = (
        build_reuse_from_source_freshness_result(
            project=project,
            adapter=adapter,
            connection=connection,
            scope=scope,
            relations=relations,
            reuse_from_snapshot=snapshot,
        )
    )
    return StandardReusePlanningResult(
        snapshot=snapshot,
        source_freshness=source_freshness,
        decisions=build_standard_reuse_decisions(
            scope=scope,
            expected_version_hashes=expected_version_hashes,
            built_fingerprints=built_fingerprints,
            reuse_from_snapshot=snapshot,
            destination_relation_names=destination_relation_names,
            cursor_snapshots=cursor_snapshots,
            reuse_from_source_freshness=source_freshness,
            custom_prepare_version_materializations=custom_prepare_version_materializations,
        ),
    )


def serialize_standard_reuse_metadata(
    result: StandardReusePlanningResult,
) -> dict[str, object]:
    """Serialize standard reuse planning diagnostics into plan metadata."""

    return {
        "standard_reuse_from_target": {
            "reuse_from_target_name": result.snapshot.reuse_from_target_name,
            "hard_copy": result.snapshot.hard_copy,
            "model_origins": {
                model_name: {
                    "database": model_snapshot.reuse_origin.database,
                    "schema": model_snapshot.reuse_origin.schema,
                    "name": model_snapshot.reuse_origin.name,
                    "qualified_name": model_snapshot.reuse_origin.qualified_name,
                    "reuse_origin_fingerprint_database": (
                        model_snapshot.reuse_origin_fingerprint_database
                    ),
                    "reuse_origin_fingerprint_schema": (
                        model_snapshot.reuse_origin_fingerprint_schema
                    ),
                    "relation_exists": model_snapshot.relation_exists,
                    "built_version_present": model_snapshot.built_version_hash is not None,
                }
                for model_name, model_snapshot in sorted(result.snapshot.model_snapshots.items())
            },
        },
        "standard_reuse_decisions": {
            "reuse_from_target_name": result.decisions.reuse_from_target_name,
            "models": {
                model_name: {
                    "decision": decision.decision,
                    "reuse_from_target_name": decision.reuse_from_target_name,
                    "reuse_origin_relation_exists": decision.reuse_origin_relation_exists,
                    "reuse_origin_built_version_present": (
                        decision.reuse_origin_built_version_present
                    ),
                    "reuse_origin_matches_expected": decision.reuse_origin_matches_expected,
                    "reuse_origin_fingerprint_database": (
                        decision.reuse_origin_fingerprint_database
                    ),
                    "reuse_origin_fingerprint_schema": decision.reuse_origin_fingerprint_schema,
                    "reuse_from_source_freshness_current": (
                        decision.reuse_from_source_freshness_current
                    ),
                }
                for model_name, decision in sorted(result.decisions.models.items())
            },
        },
    }


def serialize_standard_reuse_plan_metadata(
    *,
    model_entries: tuple[ModelPlanEntry, ...],
    dependency_baseline_entries: tuple[DependencyBaselinePlanEntry, ...],
    existing_destination_input_entries: tuple[ExistingDestinationInputPlanEntry, ...],
) -> dict[str, object]:
    """Serialize user-facing standard reuse categories into plan metadata."""

    return {
        "standard_reuse": {
            "cloned_selected": tuple(
                _serialize_cloned_selected_entry(entry)
                for entry in model_entries
                if entry.relation_reuse is not None
            ),
            "reused_inputs": tuple(
                _serialize_dependency_input_entry(entry) for entry in dependency_baseline_entries
            ),
            "existing_destination_inputs": tuple(
                _serialize_existing_destination_input_entry(entry)
                for entry in existing_destination_input_entries
            ),
        }
    }


def _serialize_cloned_selected_entry(entry: ModelPlanEntry) -> dict[str, object]:
    relation_reuse: RelationReusePlan | None = entry.relation_reuse
    if relation_reuse is None:
        return {"name": entry.name}
    return {
        "name": entry.name,
        "reuse_from_target": relation_reuse.reuse_from_target_name,
        "origin_relation": relation_reuse.origin.qualified_name,
        "hard_copy": relation_reuse.hard_copy,
    }


def _serialize_dependency_input_entry(entry: DependencyBaselinePlanEntry) -> dict[str, object]:
    return {
        "name": entry.name,
        "reuse_from_target": entry.relation_reuse.reuse_from_target_name,
        "origin_relation": entry.relation_reuse.origin.qualified_name,
        "hard_copy": entry.relation_reuse.hard_copy,
    }


def _serialize_existing_destination_input_entry(
    entry: ExistingDestinationInputPlanEntry,
) -> dict[str, object]:
    return {
        "name": entry.name,
        "destination": entry.destination.qualified_name,
        "status": entry.status,
    }
