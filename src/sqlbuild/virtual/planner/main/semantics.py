"""Public virtual planning semantics entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.models import RunDespiteUnchangedPlanningResult
from sqlbuild.compiler.planner.types import PlanReason
from sqlbuild.virtual.planner.helpers.planning import (
    build_bound_local_hashes,
    build_bound_version_hashes,
    build_default_virtual_selection,
    build_expected_local_hashes,
    build_expected_version_hashes,
    build_model_fingerprint_metadata_jsons,
    build_source_freshness_incomplete_model_names,
    build_source_version_hashes,
    build_stale_model_names,
    build_stale_root_cause_reasons,
    build_stale_root_causes,
    build_stale_root_reasons,
    build_stale_root_source_causes,
)
from sqlbuild.virtual.planner.helpers.run_despite_unchanged import (
    build_virtual_run_despite_unchanged_planning_result,
)
from sqlbuild.virtual.planner.helpers.state_metadata import (
    decode_model_version_metadata_jsons,
    decode_model_version_query_sqls,
)
from sqlbuild.virtual.planner.models import VirtualPlanSemantics
from sqlbuild.virtual.state.models import (
    ModelVersionRecord,
    SourceFreshnessRecord,
    VirtualEnvironmentModelRefRecord,
)


def build_virtual_plan_semantics(
    *,
    graph: ProjectGraph,
    bound_refs: tuple[VirtualEnvironmentModelRefRecord, ...],
    bound_model_versions: dict[str, ModelVersionRecord | None],
    source_freshness_records: tuple[SourceFreshnessRecord, ...] = (),
) -> VirtualPlanSemantics:
    """Derive expected hashes, bound hashes, stale models, and stale roots."""

    expected_local_hashes: dict[str, str] = build_expected_local_hashes(graph=graph)
    expected_metadata_jsons: dict[str, str] = build_model_fingerprint_metadata_jsons(graph=graph)
    source_version_hashes: dict[str, str] = build_source_version_hashes(source_freshness_records)
    source_freshness_incomplete_model_names: tuple[str, ...] = (
        build_source_freshness_incomplete_model_names(
            graph=graph,
            source_version_hashes=source_version_hashes,
        )
    )
    expected_version_hashes: dict[str, str] = build_expected_version_hashes(
        graph=graph,
        expected_local_hashes=expected_local_hashes,
        source_version_hashes=source_version_hashes,
    )
    bound_version_hashes: dict[str, str] = build_bound_version_hashes(bound_refs)
    bound_local_hashes: dict[str, str] = build_bound_local_hashes(bound_model_versions)
    bound_previous_query_sqls: dict[str, str] = decode_model_version_query_sqls(
        bound_model_versions
    )
    bound_metadata_jsons: dict[str, str] = decode_model_version_metadata_jsons(bound_model_versions)
    identity_stale_model_names: tuple[str, ...] = build_stale_model_names(
        model_names=tuple(model.name for model in graph.project.models),
        expected_version_hashes=expected_version_hashes,
        bound_version_hashes=bound_version_hashes,
        source_freshness_incomplete_model_names=source_freshness_incomplete_model_names,
    )
    run_despite_unchanged: RunDespiteUnchangedPlanningResult = (
        build_virtual_run_despite_unchanged_planning_result(
            graph=graph,
            source_freshness_records=source_freshness_records,
            already_stale_model_names=frozenset(identity_stale_model_names),
        )
    )
    stale_model_names: tuple[str, ...] = tuple(
        sorted(set(identity_stale_model_names) | set(run_despite_unchanged.stale_model_names))
    )
    stale_root_reasons: dict[str, PlanReason] = build_stale_root_reasons(
        stale_model_names=identity_stale_model_names,
        expected_local_hashes=expected_local_hashes,
        bound_version_hashes=bound_version_hashes,
        bound_local_hashes=bound_local_hashes,
        current_query_sqls={model.name: model.query_sql for model in graph.project.models},
        bound_previous_query_sqls=bound_previous_query_sqls,
        expected_metadata_jsons=expected_metadata_jsons,
        bound_metadata_jsons=bound_metadata_jsons,
    )
    stale_root_reasons = {
        **stale_root_reasons,
        **{
            model_name: PlanReason.RUN_DESPITE_UNCHANGED
            for model_name in run_despite_unchanged.root_model_names
        },
    }
    stale_root_source_causes: dict[str, str] = build_stale_root_source_causes(
        stale_root_reasons=stale_root_reasons,
        expected_metadata_jsons=expected_metadata_jsons,
        bound_metadata_jsons=bound_metadata_jsons,
    )
    stale_root_causes: dict[str, str] = build_stale_root_causes(
        stale_model_names=stale_model_names,
        stale_root_reasons=stale_root_reasons,
        graph=graph,
        stale_root_source_causes=stale_root_source_causes,
    )
    stale_root_cause_reasons: dict[str, PlanReason] = build_stale_root_cause_reasons(
        stale_root_reasons=stale_root_reasons,
        stale_root_source_causes=stale_root_source_causes,
    )
    return VirtualPlanSemantics(
        expected_local_hashes=expected_local_hashes,
        expected_metadata_jsons=expected_metadata_jsons,
        expected_version_hashes=expected_version_hashes,
        bound_version_hashes=bound_version_hashes,
        bound_local_hashes=bound_local_hashes,
        bound_previous_query_sqls=bound_previous_query_sqls,
        bound_metadata_jsons=bound_metadata_jsons,
        source_freshness_observed_source_names=tuple(sorted(source_version_hashes)),
        source_freshness_incomplete_source_names=tuple(
            sorted(
                source.name
                for source in graph.project.sources
                if source.name not in source_version_hashes
            )
        ),
        source_freshness_incomplete_model_names=source_freshness_incomplete_model_names,
        stale_model_names=stale_model_names,
        default_selection=build_default_virtual_selection(
            stale_model_names=stale_model_names,
            graph=graph,
        ),
        run_despite_unchanged=run_despite_unchanged,
        stale_root_reasons=stale_root_reasons,
        stale_root_causes=stale_root_causes,
        stale_root_cause_reasons=stale_root_cause_reasons,
    )
