"""Public virtual planning semantics entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.virtual.planner._helpers.semantics_facts import (
    build_bound_identity_facts,
    build_expected_identity_facts,
    build_staleness_facts,
)
from sqlbuild.virtual.planner.models import (
    BoundIdentityFacts,
    ExpectedIdentityFacts,
    StalenessFacts,
    VirtualPlanSemantics,
)
from sqlbuild.virtual.state.models import (
    ModelVersionRecord,
    SourceFreshnessRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentSeedRefRecord,
)


def build_virtual_plan_semantics(
    *,
    graph: ProjectGraph,
    bound_refs: tuple[VirtualEnvironmentModelRefRecord, ...],
    bound_model_versions: dict[str, ModelVersionRecord | None],
    bound_seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...] = (),
    source_freshness_records: tuple[SourceFreshnessRecord, ...] = (),
) -> VirtualPlanSemantics:
    """Derive expected hashes, bound hashes, stale models, and stale roots."""

    expected: ExpectedIdentityFacts = build_expected_identity_facts(
        graph=graph,
        source_freshness_records=source_freshness_records,
    )
    bound: BoundIdentityFacts = build_bound_identity_facts(
        bound_refs=bound_refs,
        bound_model_versions=bound_model_versions,
        bound_seed_refs=bound_seed_refs,
    )
    staleness: StalenessFacts = build_staleness_facts(
        graph=graph,
        expected=expected,
        bound=bound,
        source_freshness_records=source_freshness_records,
    )
    return VirtualPlanSemantics(
        expected_local_hashes=expected.local_hashes,
        expected_metadata_jsons=expected.metadata_jsons,
        expected_version_hashes=expected.version_hashes,
        expected_seed_version_hashes=expected.seed_version_hashes,
        seed_identity_metadata_jsons=expected.seed_identity_metadata_jsons,
        bound_version_hashes=bound.version_hashes,
        bound_seed_version_hashes=bound.seed_version_hashes,
        bound_local_hashes=bound.local_hashes,
        bound_previous_query_sqls=bound.previous_query_sqls,
        bound_metadata_jsons=bound.metadata_jsons,
        source_freshness_observed_source_names=expected.source_freshness_observed_source_names,
        source_freshness_incomplete_source_names=expected.source_freshness_incomplete_source_names,
        source_freshness_incomplete_model_names=expected.source_freshness_incomplete_model_names,
        stale_seed_names=staleness.stale_seed_names,
        seed_plan_reasons=staleness.seed_plan_reasons,
        stale_model_names=staleness.stale_model_names,
        default_selection=staleness.default_selection,
        run_despite_unchanged=staleness.run_despite_unchanged,
        stale_root_reasons=staleness.stale_root_reasons,
        stale_root_causes=staleness.stale_root_causes,
        stale_root_cause_reasons=staleness.stale_root_cause_reasons,
    )
