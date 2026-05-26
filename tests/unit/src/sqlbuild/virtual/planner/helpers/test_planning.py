from __future__ import annotations

import pytest

from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.types import PlanReason
from sqlbuild.virtual.planner.helpers.planning import (
    build_default_virtual_selection,
    build_expected_local_hashes,
    build_expected_version_hashes,
    build_stale_model_names,
    build_stale_root_causes,
    build_stale_root_reasons,
)
from tests.unit.src.sqlbuild.virtual.planner.helpers._test_types import (
    DefaultVirtualSelectionTestCase,
    ExpectedVersionHashesTestCase,
    StaleModelNamesTestCase,
    StaleRootCausesTestCase,
    StaleRootReasonsTestCase,
)
from tests.unit.src.sqlbuild.virtual.planner.helpers.helpers import (
    build_virtual_planner_test_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ExpectedVersionHashesTestCase(
            description="upstream query change changes downstream expected hash",
            upstream_query_sql="SELECT 1 AS id",
            downstream_query_sql="SELECT id FROM stg_orders",
            expected_hashes_differ=True,
        )
    ],
    ids=["upstream query change changes downstream expected hash"],
)
def test_given_upstream_change_when_building_expected_hashes_then_downstream_hash_changes(
    test_case: ExpectedVersionHashesTestCase,
) -> None:
    baseline_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql="SELECT 0 AS id",
        downstream_query_sql=test_case.downstream_query_sql,
    )
    changed_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
    )

    baseline_hashes: dict[str, str] = build_expected_version_hashes(
        graph=baseline_graph,
        expected_local_hashes=build_expected_local_hashes(graph=baseline_graph),
    )
    changed_hashes: dict[str, str] = build_expected_version_hashes(
        graph=changed_graph,
        expected_local_hashes=build_expected_local_hashes(graph=changed_graph),
    )

    assert (
        baseline_hashes["fact_orders"] != changed_hashes["fact_orders"]
    ) is test_case.expected_hashes_differ


@pytest.mark.parametrize(
    "test_case",
    [
        DefaultVirtualSelectionTestCase(
            description="selects stale models plus downstream closure only",
            stale_model_names=("stg_orders",),
            expected_selection=("fact_orders", "stg_orders"),
        )
    ],
    ids=["selects stale models plus downstream closure only"],
)
def test_given_stale_models_when_building_default_selection_then_it_includes_downstream_only(
    test_case: DefaultVirtualSelectionTestCase,
) -> None:
    graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql="SELECT 1 AS id",
        downstream_query_sql="SELECT id FROM stg_orders",
    )

    selection: tuple[str, ...] = build_default_virtual_selection(
        stale_model_names=test_case.stale_model_names,
        graph=graph,
    )

    assert selection == test_case.expected_selection


@pytest.mark.parametrize(
    "test_case",
    [
        StaleModelNamesTestCase(
            description="marks only mismatched bound hashes as stale",
            expected_version_hashes={
                "stg_orders": "current-a",
                "fact_orders": "current-b",
                "dim_customers": "current-c",
            },
            bound_version_hashes={
                "stg_orders": "old-a",
                "fact_orders": "current-b",
                "dim_customers": "current-c",
            },
            expected_stale_model_names=("stg_orders",),
        )
    ],
    ids=["marks only mismatched bound hashes as stale"],
)
def test_given_bound_hash_mismatch_when_building_stale_models_then_it_marks_only_mismatches(
    test_case: StaleModelNamesTestCase,
) -> None:
    stale_model_names: tuple[str, ...] = build_stale_model_names(
        model_names=("stg_orders", "fact_orders", "dim_customers"),
        expected_version_hashes=test_case.expected_version_hashes,
        bound_version_hashes=test_case.bound_version_hashes,
    )

    assert stale_model_names == test_case.expected_stale_model_names


@pytest.mark.parametrize(
    "test_case",
    [
        StaleRootReasonsTestCase(
            description="classifies first run and query changed stale roots",
            stale_model_names=("stg_orders", "fact_orders", "dim_customers"),
            expected_local_hashes={
                "stg_orders": "new-local-a",
                "fact_orders": "same-local-b",
                "dim_customers": "new-local-c",
            },
            bound_version_hashes={
                "stg_orders": "old-version-a",
                "fact_orders": "old-version-b",
            },
            bound_local_hashes={
                "stg_orders": "old-local-a",
                "fact_orders": "same-local-b",
            },
            expected_stale_root_reasons={
                "stg_orders": PlanReason.QUERY_CHANGED,
                "dim_customers": PlanReason.FIRST_RUN,
            },
        )
    ],
    ids=["classifies first run and query changed stale roots"],
)
def test_given_stale_models_when_building_stale_root_reasons_then_it_classifies_roots(
    test_case: StaleRootReasonsTestCase,
) -> None:
    stale_root_reasons: dict[str, PlanReason] = build_stale_root_reasons(
        stale_model_names=test_case.stale_model_names,
        expected_local_hashes=test_case.expected_local_hashes,
        bound_version_hashes=test_case.bound_version_hashes,
        bound_local_hashes=test_case.bound_local_hashes,
    )

    assert stale_root_reasons == test_case.expected_stale_root_reasons


@pytest.mark.parametrize(
    "test_case",
    [
        StaleRootCausesTestCase(
            description="maps downstream stale models to their first stale root cause",
            stale_model_names=("stg_orders", "fact_orders"),
            stale_root_reasons={"stg_orders": PlanReason.QUERY_CHANGED},
            expected_stale_root_causes={"fact_orders": "stg_orders"},
        )
    ],
    ids=["maps downstream stale models to their first stale root cause"],
)
def test_given_stale_roots_when_building_root_causes_then_it_maps_downstream_models(
    test_case: StaleRootCausesTestCase,
) -> None:
    graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql="SELECT 1 AS id",
        downstream_query_sql="SELECT id FROM stg_orders",
    )

    stale_root_causes: dict[str, str] = build_stale_root_causes(
        stale_model_names=test_case.stale_model_names,
        stale_root_reasons=test_case.stale_root_reasons,
        graph=graph,
    )

    assert stale_root_causes == test_case.expected_stale_root_causes
