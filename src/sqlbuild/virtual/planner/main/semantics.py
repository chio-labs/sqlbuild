"""Public virtual planning semantics entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.types import PlanReason
from sqlbuild.virtual.planner.helpers.planning import (
    build_bound_local_hashes,
    build_bound_version_hashes,
    build_default_virtual_selection,
    build_expected_local_hashes,
    build_expected_version_hashes,
    build_model_fingerprint_metadata_jsons,
    build_stale_model_names,
    build_stale_root_causes,
    build_stale_root_reasons,
)
from sqlbuild.virtual.planner.models import VirtualPlanSemantics
from sqlbuild.virtual.shared.helpers.encoding import decode_state_text
from sqlbuild.virtual.state.models import ModelVersionRecord, VirtualEnvironmentRefRecord


def build_virtual_plan_semantics(
    *,
    graph: ProjectGraph,
    bound_refs: tuple[VirtualEnvironmentRefRecord, ...],
    bound_model_versions: dict[str, ModelVersionRecord | None],
) -> VirtualPlanSemantics:
    """Derive expected hashes, bound hashes, stale models, and stale roots."""

    expected_local_hashes: dict[str, str] = build_expected_local_hashes(graph=graph)
    expected_metadata_jsons: dict[str, str] = build_model_fingerprint_metadata_jsons(graph=graph)
    expected_version_hashes: dict[str, str] = build_expected_version_hashes(
        graph=graph,
        expected_local_hashes=expected_local_hashes,
    )
    bound_version_hashes: dict[str, str] = build_bound_version_hashes(bound_refs)
    bound_local_hashes: dict[str, str] = build_bound_local_hashes(bound_model_versions)
    bound_previous_query_sqls: dict[str, str] = {
        model_name: query_sql
        for model_name, model_version in bound_model_versions.items()
        if model_version is not None
        for query_sql in (decode_state_text(model_version.fingerprint_query_sql_b64),)
        if query_sql is not None
    }
    stale_model_names: tuple[str, ...] = build_stale_model_names(
        model_names=tuple(model.name for model in graph.project.models),
        expected_version_hashes=expected_version_hashes,
        bound_version_hashes=bound_version_hashes,
    )
    stale_root_reasons: dict[str, PlanReason] = build_stale_root_reasons(
        stale_model_names=stale_model_names,
        expected_local_hashes=expected_local_hashes,
        bound_version_hashes=bound_version_hashes,
        bound_local_hashes=bound_local_hashes,
    )
    return VirtualPlanSemantics(
        expected_local_hashes=expected_local_hashes,
        expected_metadata_jsons=expected_metadata_jsons,
        expected_version_hashes=expected_version_hashes,
        bound_version_hashes=bound_version_hashes,
        bound_local_hashes=bound_local_hashes,
        bound_previous_query_sqls=bound_previous_query_sqls,
        stale_model_names=stale_model_names,
        default_selection=build_default_virtual_selection(
            stale_model_names=stale_model_names,
            graph=graph,
        ),
        stale_root_reasons=stale_root_reasons,
        stale_root_causes=build_stale_root_causes(
            stale_model_names=stale_model_names,
            stale_root_reasons=stale_root_reasons,
            graph=graph,
        ),
    )
