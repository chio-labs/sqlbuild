"""Standard target reuse planner orchestration helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.helpers.source_freshness import (
    build_reuse_from_source_freshness_result,
)
from sqlbuild.compiler.planner.helpers.standard_reuse_decisions import (
    build_standard_reuse_decisions,
)
from sqlbuild.compiler.planner.helpers.standard_reuse_from_target import (
    build_standard_reuse_from_target_snapshot,
)
from sqlbuild.compiler.planner.models import (
    ModelCursorSnapshot,
    PlannerRelationsContext,
    PlannerScope,
    StandardReuseFromTargetSnapshot,
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
    expected_version_hashes: dict[str, str],
    built_fingerprints: dict[str, Fingerprint],
    cursor_snapshots: dict[str, ModelCursorSnapshot],
    full_refresh: bool,
    custom_prepare_version_materializations: frozenset[str] = frozenset(),
) -> StandardReusePlanningResult | None:
    """Build snapshot, freshness, and decisions for standard target reuse."""

    if full_refresh:
        return None
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
