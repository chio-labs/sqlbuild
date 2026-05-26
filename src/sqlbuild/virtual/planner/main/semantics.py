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
    build_stale_model_names,
    build_stale_root_causes,
    build_stale_root_reasons,
)
from sqlbuild.virtual.planner.models import VirtualPlanSemantics
from sqlbuild.virtual.state.models import ModelVersionRecord, VirtualEnvironmentRefRecord


def build_virtual_plan_semantics(
    *,
    graph: ProjectGraph,
    bound_refs: tuple[VirtualEnvironmentRefRecord, ...],
    bound_model_versions: dict[str, ModelVersionRecord | None],
) -> VirtualPlanSemantics:
    """Derive expected hashes, bound hashes, stale models, and stale roots."""

    expected_local_hashes: dict[str, str] = build_expected_local_hashes(graph=graph)
    expected_version_hashes: dict[str, str] = build_expected_version_hashes(
        graph=graph,
        expected_local_hashes=expected_local_hashes,
    )
    bound_version_hashes: dict[str, str] = build_bound_version_hashes(bound_refs)
    bound_local_hashes: dict[str, str] = build_bound_local_hashes(bound_model_versions)
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
        expected_version_hashes=expected_version_hashes,
        bound_version_hashes=bound_version_hashes,
        bound_local_hashes=bound_local_hashes,
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
