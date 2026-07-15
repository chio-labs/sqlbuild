"""Virtual planner bridge for run_despite_unchanged planning."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.main.changes.run_despite_unchanged import (
    build_run_despite_unchanged_planning_result,
)
from sqlbuild.compiler.planner.models import PlannerScope, RunDespiteUnchangedPlanningResult
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    StandardSourceFreshnessPlanningResult,
)
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessRecord as StandardSourceFreshnessRecord,
)
from sqlbuild.virtual.state.models import SourceFreshnessRecord


def build_virtual_run_despite_unchanged_planning_result(
    *,
    graph: ProjectGraph,
    source_freshness_records: tuple[SourceFreshnessRecord, ...],
    already_stale_model_names: frozenset[str],
) -> RunDespiteUnchangedPlanningResult:
    """Return VDE models selected by run_despite_unchanged semantics."""

    source_freshness: StandardSourceFreshnessPlanningResult = _standard_source_freshness_result(
        source_freshness_records
    )
    return build_run_despite_unchanged_planning_result(
        scope=_planner_scope_from_graph(graph),
        source_freshness=source_freshness,
        already_stale_model_names=already_stale_model_names,
        now=(
            source_freshness.observed_records[0].observed_at
            if source_freshness.observed_records
            else datetime.now(UTC)
        ),
    )


def _planner_scope_from_graph(graph: ProjectGraph) -> PlannerScope:
    return PlannerScope(
        upstream_deps=graph.upstream_deps,
        downstream_deps=graph.downstream_deps,
        all_keys=graph.all_keys,
        models_by_name={model.name: model for model in graph.project.models},
        selected_keys=frozenset(graph.all_keys.values()),
        execution_order=tuple(graph.upstream_deps),
    )


def _standard_source_freshness_result(
    records: tuple[SourceFreshnessRecord, ...],
) -> StandardSourceFreshnessPlanningResult:
    observed_records: tuple[StandardSourceFreshnessRecord, ...] = tuple(
        StandardSourceFreshnessRecord(
            source_name=record.source_name,
            target_database=None,
            target_schema=None,
            target_name=None,
            run_id=record.virtual_environment_name,
            strategy=record.strategy,
            value_kind=record.value_kind,
            data_version=record.data_version,
            data_version_hash=record.data_version_hash,
            observed_at=record.observed_at,
        )
        for record in records
    )
    return StandardSourceFreshnessPlanningResult(
        observed_records=observed_records,
        unchanged_identities=frozenset(
            SourceFreshnessIdentity(
                source_name=record.source_name,
                target_database=None,
                target_schema=None,
                target_name=None,
            )
            for record in records
        ),
    )
