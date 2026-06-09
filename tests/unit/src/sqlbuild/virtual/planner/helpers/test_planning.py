from __future__ import annotations

from datetime import datetime

import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.types import PlanReason
from sqlbuild.shared.models import SqlHookEntry
from sqlbuild.spec.models.schema import SchemaColumn
from sqlbuild.spec.models.source import SourceEntry, SourceFreshnessConfig
from sqlbuild.spec.models.types import SourceFreshnessStrategy, SourceFreshnessValueKind
from sqlbuild.virtual.freshness.helpers.runtime import (
    build_current_virtual_source_freshness_records,
)
from sqlbuild.virtual.planner.helpers.planning import (
    build_default_virtual_selection,
    build_expected_local_hashes,
    build_expected_version_hashes,
    build_model_fingerprint_metadata_jsons,
    build_source_freshness_incomplete_model_names,
    build_stale_model_names,
    build_stale_required_upstream_closure,
    build_stale_root_cause_reasons,
    build_stale_root_causes,
    build_stale_root_reasons,
    build_stale_root_source_causes,
    resolve_virtual_model_selection,
)
from sqlbuild.virtual.state.models import SourceFreshnessRecord
from tests.unit.src.sqlbuild.virtual.planner.helpers._test_types import (
    DefaultVirtualSelectionTestCase,
    ExpectedVersionHashesTestCase,
    StaleModelNamesTestCase,
    StaleRequiredUpstreamClosureTestCase,
    StaleRootCauseReasonsTestCase,
    StaleRootCausesTestCase,
    StaleRootReasonsTestCase,
    StaleRootSourceCausesTestCase,
    VirtualModelSelectionTestCase,
    VirtualSourceFreshnessLagToleranceTestCase,
)
from tests.unit.src.sqlbuild.virtual.planner.helpers.helpers import (
    build_virtual_planner_test_project,
)

VIRTUAL_MODEL_SELECTION_TEST_CASES: tuple[VirtualModelSelectionTestCase, ...] = (
    VirtualModelSelectionTestCase(
        description="include stale upstreams expands minimally",
        select=("fact_orders",),
        default_selection=("fact_orders", "stg_orders"),
        stale_model_names=("fact_orders", "stg_orders"),
        include_stale_upstreams=True,
        changes_only=False,
        expected_selection=("fact_orders", "stg_orders"),
    ),
    VirtualModelSelectionTestCase(
        description="changes only intersects selected models with default stale selection",
        select=("fact_orders", "dim_customers"),
        default_selection=("fact_orders", "stg_orders"),
        stale_model_names=("fact_orders", "stg_orders"),
        include_stale_upstreams=True,
        changes_only=True,
        expected_selection=("fact_orders", "stg_orders"),
    ),
    VirtualModelSelectionTestCase(
        description="include stale upstreams excludes unchanged upstreams",
        select=("fact_orders",),
        default_selection=("fact_orders", "stg_orders"),
        stale_model_names=("fact_orders", "stg_orders"),
        include_stale_upstreams=True,
        changes_only=False,
        expected_selection=("fact_orders", "stg_orders"),
        downstream_depends_on_dim_customers=True,
    ),
)

STALE_ROOT_REASONS_TEST_CASES: tuple[StaleRootReasonsTestCase, ...] = (
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
    ),
    StaleRootReasonsTestCase(
        description="classifies version identity config separately from function changes",
        stale_model_names=("fact_orders", "orders_rollup"),
        expected_local_hashes={
            "fact_orders": "new-local-a",
            "orders_rollup": "new-local-b",
        },
        bound_version_hashes={
            "fact_orders": "old-version-a",
            "orders_rollup": "old-version-b",
        },
        bound_local_hashes={
            "fact_orders": "old-local-a",
            "orders_rollup": "old-local-b",
        },
        current_query_sqls={
            "fact_orders": "SELECT id FROM stg_orders",
            "orders_rollup": "SELECT COUNT(*) FROM fact_orders",
        },
        bound_previous_query_sqls={
            "fact_orders": "SELECT id FROM stg_orders",
            "orders_rollup": "SELECT COUNT(*) FROM fact_orders",
        },
        expected_metadata_jsons={
            "fact_orders": '{"config":{},"local_function_hashes":{"is_large_order":"new"}}',
            "orders_rollup": '{"config":{"materialized":"table"}}',
        },
        bound_metadata_jsons={
            "fact_orders": '{"config":{},"local_function_hashes":{"is_large_order":"old"}}',
            "orders_rollup": '{"config":{"materialized":"view"}}',
        },
        expected_stale_root_reasons={
            "fact_orders": PlanReason.QUERY_CHANGED,
            "orders_rollup": PlanReason.CONFIG_CHANGED,
        },
    ),
)

STALE_ROOT_CAUSES_TEST_CASES: tuple[StaleRootCausesTestCase, ...] = (
    StaleRootCausesTestCase(
        description="maps downstream stale models to their first stale root cause",
        stale_model_names=("stg_orders", "fact_orders"),
        stale_root_reasons={"stg_orders": PlanReason.QUERY_CHANGED},
        expected_stale_root_causes={"fact_orders": "stg_orders"},
    ),
    StaleRootCausesTestCase(
        description="maps downstream stale models to changed function source cause",
        stale_model_names=("stg_orders", "fact_orders"),
        stale_root_reasons={"stg_orders": PlanReason.QUERY_CHANGED},
        stale_root_source_causes={"stg_orders": "is_large_order"},
        expected_stale_root_causes={"fact_orders": "is_large_order"},
    ),
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
        ExpectedVersionHashesTestCase(
            description="unchanged graph produces stable expected hashes",
            upstream_query_sql="SELECT 1 AS id",
            downstream_query_sql="SELECT normalize_order(id) FROM stg_orders",
            expected_hashes_differ=False,
        )
    ],
    ids=["unchanged graph produces stable expected hashes"],
)
def test_given_unchanged_graph_when_building_expected_hashes_then_hashes_match(
    test_case: ExpectedVersionHashesTestCase,
) -> None:
    first_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
    )
    second_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
    )

    first_hashes: dict[str, str] = build_expected_version_hashes(
        graph=first_graph,
        expected_local_hashes=build_expected_local_hashes(graph=first_graph),
    )
    second_hashes: dict[str, str] = build_expected_version_hashes(
        graph=second_graph,
        expected_local_hashes=build_expected_local_hashes(graph=second_graph),
    )

    assert (
        first_hashes["fact_orders"] != second_hashes["fact_orders"]
    ) is test_case.expected_hashes_differ


@pytest.mark.parametrize(
    "test_case",
    [
        ExpectedVersionHashesTestCase(
            description="function body change updates dependent expected hash",
            upstream_query_sql="SELECT 1 AS id",
            downstream_query_sql="SELECT normalize_order(id) FROM stg_orders",
            expected_hashes_differ=True,
        )
    ],
    ids=["function body change updates dependent expected hash"],
)
def test_given_function_change_when_building_expected_hashes_then_downstream_hash_changes(
    test_case: ExpectedVersionHashesTestCase,
) -> None:
    baseline_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
        function_body_sql="value + 1",
    )
    changed_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
        function_body_sql="value + 2",
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
        ExpectedVersionHashesTestCase(
            description="source data version change updates downstream expected hash",
            upstream_query_sql="SELECT * FROM __source('raw.orders')",
            downstream_query_sql="SELECT id FROM stg_orders",
            expected_hashes_differ=True,
        )
    ],
    ids=["source data version change updates downstream expected hash"],
)
def test_given_source_data_version_change_when_building_hashes_then_downstream_hash_changes(
    test_case: ExpectedVersionHashesTestCase,
) -> None:
    graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
    )

    baseline_hashes: dict[str, str] = build_expected_version_hashes(
        graph=graph,
        expected_local_hashes=build_expected_local_hashes(graph=graph),
        source_version_hashes={"raw.orders": "source-version-1"},
    )
    changed_hashes: dict[str, str] = build_expected_version_hashes(
        graph=graph,
        expected_local_hashes=build_expected_local_hashes(graph=graph),
        source_version_hashes={"raw.orders": "source-version-2"},
    )

    assert (
        baseline_hashes["stg_orders"] != changed_hashes["stg_orders"]
    ) is test_case.expected_hashes_differ
    assert (
        baseline_hashes["fact_orders"] != changed_hashes["fact_orders"]
    ) is test_case.expected_hashes_differ


VIRTUAL_LAG_TOLERANCE_TEST_CASES: tuple[VirtualSourceFreshnessLagToleranceTestCase, ...] = (
    VirtualSourceFreshnessLagToleranceTestCase(
        description="virtual preserves previous within tolerance",
        current_data_version="2026-01-15T12:05:00",
        expected_record_data_version="2026-01-15T12:00:00",
    ),
    VirtualSourceFreshnessLagToleranceTestCase(
        description="virtual preserves previous at tolerance boundary",
        current_data_version="2026-01-15T12:10:00",
        expected_record_data_version="2026-01-15T12:00:00",
    ),
    VirtualSourceFreshnessLagToleranceTestCase(
        description="virtual uses current beyond tolerance",
        current_data_version="2026-01-15T12:11:00",
        expected_record_data_version="2026-01-15T12:11:00",
    ),
    VirtualSourceFreshnessLagToleranceTestCase(
        description="virtual uses current for backwards timestamp movement",
        current_data_version="2026-01-15T11:59:00",
        expected_record_data_version="2026-01-15T11:59:00",
    ),
)


@pytest.mark.parametrize(
    "test_case",
    VIRTUAL_LAG_TOLERANCE_TEST_CASES,
    ids=[case.description for case in VIRTUAL_LAG_TOLERANCE_TEST_CASES],
)
def test_given_virtual_lag_tolerance_when_building_current_records_then_preserves_baseline(
    test_case: VirtualSourceFreshnessLagToleranceTestCase,
) -> None:
    previous_data_version: str = "2026-01-15T12:00:00"
    previous_record: SourceFreshnessRecord = SourceFreshnessRecord(
        virtual_environment_name="dev",
        source_name="raw.orders",
        strategy=SourceFreshnessStrategy.SQL.value,
        value_kind=SourceFreshnessValueKind.TIMESTAMP.value,
        data_version=previous_data_version,
        data_version_hash="previous-hash",
        observed_at=datetime(2026, 1, 15, 12, 0, 0),
    )
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: object = adapter.connect({"database": ":memory:"})
    try:
        records: tuple[SourceFreshnessRecord, ...] = build_current_virtual_source_freshness_records(
            adapter=adapter,
            connection=connection,
            sources=(
                SourceEntry(
                    name="raw.orders",
                    freshness=SourceFreshnessConfig(
                        strategy=SourceFreshnessStrategy.SQL,
                        value_kind=SourceFreshnessValueKind.TIMESTAMP,
                        query=f"SELECT CAST('{test_case.current_data_version}' AS TIMESTAMP)",
                        lag_tolerance="10m",
                    ),
                ),
            ),
            virtual_environment_name="dev",
            observed_at=datetime(2026, 1, 15, 12, 30, 0),
            previous_records=(previous_record,),
        )
    finally:
        adapter.close(connection)

    assert records[0].data_version == test_case.expected_record_data_version


@pytest.mark.parametrize(
    "test_case",
    [
        ExpectedVersionHashesTestCase(
            description="unchanged source data version keeps downstream expected hash stable",
            upstream_query_sql="SELECT * FROM __source('raw.orders')",
            downstream_query_sql="SELECT id FROM stg_orders",
            expected_hashes_differ=False,
        )
    ],
    ids=["unchanged source data version keeps downstream expected hash stable"],
)
def test_given_same_source_data_version_when_building_expected_hashes_then_hashes_match(
    test_case: ExpectedVersionHashesTestCase,
) -> None:
    first_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
    )
    second_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
    )

    first_hashes: dict[str, str] = build_expected_version_hashes(
        graph=first_graph,
        expected_local_hashes=build_expected_local_hashes(graph=first_graph),
        source_version_hashes={"raw.orders": "source-version-1"},
    )
    second_hashes: dict[str, str] = build_expected_version_hashes(
        graph=second_graph,
        expected_local_hashes=build_expected_local_hashes(graph=second_graph),
        source_version_hashes={"raw.orders": "source-version-1"},
    )

    assert (
        first_hashes["fact_orders"] != second_hashes["fact_orders"]
    ) is test_case.expected_hashes_differ


@pytest.mark.parametrize(
    "test_case",
    [
        StaleModelNamesTestCase(
            description="source data version change marks direct and transitive models stale",
            expected_version_hashes={},
            bound_version_hashes={},
            expected_stale_model_names=("stg_orders", "fact_orders"),
        )
    ],
    ids=["source data version change marks direct and transitive models stale"],
)
def test_given_source_data_version_change_when_building_stale_models_then_marks_downstream_stale(
    test_case: StaleModelNamesTestCase,
) -> None:
    graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql="SELECT * FROM __source('raw.orders')",
        downstream_query_sql="SELECT id FROM stg_orders",
        upstream_materialized="view",
    )
    expected_local_hashes: dict[str, str] = build_expected_local_hashes(graph=graph)
    bound_hashes: dict[str, str] = build_expected_version_hashes(
        graph=graph,
        expected_local_hashes=expected_local_hashes,
        source_version_hashes={"raw.orders": "source-version-1"},
    )
    expected_hashes: dict[str, str] = build_expected_version_hashes(
        graph=graph,
        expected_local_hashes=expected_local_hashes,
        source_version_hashes={"raw.orders": "source-version-2"},
    )

    stale_model_names: tuple[str, ...] = build_stale_model_names(
        model_names=tuple(model.name for model in graph.project.models),
        expected_version_hashes=expected_hashes,
        bound_version_hashes=bound_hashes,
    )

    assert stale_model_names == test_case.expected_stale_model_names


@pytest.mark.parametrize(
    "test_case",
    [
        StaleRequiredUpstreamClosureTestCase(
            description="missing source freshness marks direct and downstream models incomplete",
            selected_model_names=(),
            stale_model_names=(),
            expected_stale_upstream_names=("fact_orders", "stg_orders"),
        )
    ],
    ids=["missing source freshness marks direct and downstream models incomplete"],
)
def test_given_missing_source_freshness_when_finding_incomplete_models_then_returns_closure(
    test_case: StaleRequiredUpstreamClosureTestCase,
) -> None:
    graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql="SELECT * FROM __source('raw.orders')",
        downstream_query_sql="SELECT id FROM stg_orders",
    )

    incomplete_model_names: tuple[str, ...] = build_source_freshness_incomplete_model_names(
        graph=graph,
        source_version_hashes={},
    )

    assert incomplete_model_names == test_case.expected_stale_upstream_names


@pytest.mark.parametrize(
    "test_case",
    [
        ExpectedVersionHashesTestCase(
            description="target schema does not change model version hash",
            upstream_query_sql="SELECT 1 AS id",
            downstream_query_sql="SELECT 1 AS order_id",
            expected_hashes_differ=False,
        )
    ],
    ids=["target schema does not change model version hash"],
)
def test_given_only_target_schema_differs_when_building_expected_hashes_then_hashes_match(
    test_case: ExpectedVersionHashesTestCase,
) -> None:
    prod_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
        upstream_schema="prod",
    )
    dev_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
        upstream_schema="dev",
    )

    prod_hashes: dict[str, str] = build_expected_version_hashes(
        graph=prod_graph,
        expected_local_hashes=build_expected_local_hashes(graph=prod_graph),
    )
    dev_hashes: dict[str, str] = build_expected_version_hashes(
        graph=dev_graph,
        expected_local_hashes=build_expected_local_hashes(graph=dev_graph),
    )
    prod_metadata_jsons: dict[str, str] = build_model_fingerprint_metadata_jsons(graph=prod_graph)

    assert (
        prod_hashes["stg_orders"] != dev_hashes["stg_orders"]
    ) is test_case.expected_hashes_differ
    assert '"schema"' not in prod_metadata_jsons["stg_orders"]


@pytest.mark.parametrize(
    "test_case",
    [
        ExpectedVersionHashesTestCase(
            description="model identity changes model version hash",
            upstream_query_sql="SELECT 1 AS id",
            downstream_query_sql="SELECT 1 AS order_id",
            expected_hashes_differ=True,
        )
    ],
    ids=["model identity changes model version hash"],
)
def test_given_only_model_name_differs_when_building_expected_hashes_then_hashes_differ(
    test_case: ExpectedVersionHashesTestCase,
) -> None:
    first_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
        upstream_model_name="stg_orders",
    )
    second_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
        upstream_model_name="stg_orders_copy",
    )

    first_hashes: dict[str, str] = build_expected_version_hashes(
        graph=first_graph,
        expected_local_hashes=build_expected_local_hashes(graph=first_graph),
    )
    second_hashes: dict[str, str] = build_expected_version_hashes(
        graph=second_graph,
        expected_local_hashes=build_expected_local_hashes(graph=second_graph),
    )

    assert (
        first_hashes["stg_orders"] != second_hashes["stg_orders_copy"]
    ) is test_case.expected_hashes_differ


@pytest.mark.parametrize(
    "test_case",
    [
        ExpectedVersionHashesTestCase(
            description="unknown validation config keys do not change model version hash",
            upstream_query_sql="SELECT 1 AS id",
            downstream_query_sql="SELECT 1 AS order_id",
            expected_hashes_differ=False,
        )
    ],
    ids=["unknown validation config keys do not change model version hash"],
)
def test_given_validation_config_keys_when_building_expected_hashes_then_hashes_match(
    test_case: ExpectedVersionHashesTestCase,
) -> None:
    baseline_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
    )
    extra_config_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
        upstream_extra_config={
            "audits": ["not_null(order_id)"],
            "contract": "enforced",
            "future_default_flag": "off",
            "mode": "strict",
        },
    )

    baseline_hashes: dict[str, str] = build_expected_version_hashes(
        graph=baseline_graph,
        expected_local_hashes=build_expected_local_hashes(graph=baseline_graph),
    )
    extra_config_hashes: dict[str, str] = build_expected_version_hashes(
        graph=extra_config_graph,
        expected_local_hashes=build_expected_local_hashes(graph=extra_config_graph),
    )
    metadata_jsons: dict[str, str] = build_model_fingerprint_metadata_jsons(
        graph=extra_config_graph
    )

    assert (
        baseline_hashes["stg_orders"] != extra_config_hashes["stg_orders"]
    ) is test_case.expected_hashes_differ
    assert "audits" not in metadata_jsons["stg_orders"]
    assert "contract" not in metadata_jsons["stg_orders"]
    assert "future_default_flag" not in metadata_jsons["stg_orders"]
    assert '"mode"' not in metadata_jsons["stg_orders"]


@pytest.mark.parametrize(
    "test_case",
    [
        ExpectedVersionHashesTestCase(
            description="incremental mode changes model version hash",
            upstream_query_sql="SELECT 1 AS id",
            downstream_query_sql="SELECT 1 AS order_id",
            expected_hashes_differ=True,
        )
    ],
    ids=["incremental mode changes model version hash"],
)
def test_given_incremental_mode_when_building_expected_hashes_then_hashes_differ(
    test_case: ExpectedVersionHashesTestCase,
) -> None:
    baseline_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
        upstream_extra_config={"incremental_mode": "normal"},
    )
    microbatch_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
        upstream_extra_config={"incremental_mode": "microbatch"},
    )

    baseline_hashes: dict[str, str] = build_expected_version_hashes(
        graph=baseline_graph,
        expected_local_hashes=build_expected_local_hashes(graph=baseline_graph),
    )
    microbatch_hashes: dict[str, str] = build_expected_version_hashes(
        graph=microbatch_graph,
        expected_local_hashes=build_expected_local_hashes(graph=microbatch_graph),
    )

    assert (
        baseline_hashes["stg_orders"] != microbatch_hashes["stg_orders"]
    ) is test_case.expected_hashes_differ


@pytest.mark.parametrize(
    "test_case",
    [
        ExpectedVersionHashesTestCase(
            description="version identity config key changes model version hash",
            upstream_query_sql="SELECT 1 AS id",
            downstream_query_sql="SELECT 1 AS order_id",
            expected_hashes_differ=True,
        )
    ],
    ids=["version identity config key changes model version hash"],
)
def test_given_version_identity_config_key_when_building_expected_hashes_then_hashes_differ(
    test_case: ExpectedVersionHashesTestCase,
) -> None:
    table_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
        upstream_materialized="table",
    )
    view_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
        upstream_materialized="view",
    )

    table_hashes: dict[str, str] = build_expected_version_hashes(
        graph=table_graph,
        expected_local_hashes=build_expected_local_hashes(graph=table_graph),
    )
    view_hashes: dict[str, str] = build_expected_version_hashes(
        graph=view_graph,
        expected_local_hashes=build_expected_local_hashes(graph=view_graph),
    )

    assert (
        table_hashes["stg_orders"] != view_hashes["stg_orders"]
    ) is test_case.expected_hashes_differ


@pytest.mark.parametrize(
    "test_case",
    [
        ExpectedVersionHashesTestCase(
            description="enforced contract output shape changes model version hash",
            upstream_query_sql="SELECT 1 AS id",
            downstream_query_sql="SELECT 1 AS order_id",
            expected_hashes_differ=True,
        )
    ],
    ids=["enforced contract output shape changes model version hash"],
)
def test_given_enforced_contract_shape_change_when_building_expected_hashes_then_hashes_differ(
    test_case: ExpectedVersionHashesTestCase,
) -> None:
    int_contract_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
        upstream_extra_config={"contract": "enforced"},
        upstream_schema_columns=(SchemaColumn(name="id", type="INTEGER", nullable=False),),
    )
    string_contract_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
        upstream_extra_config={"contract": "enforced"},
        upstream_schema_columns=(SchemaColumn(name="id", type="TEXT", nullable=False),),
    )

    int_hashes: dict[str, str] = build_expected_version_hashes(
        graph=int_contract_graph,
        expected_local_hashes=build_expected_local_hashes(graph=int_contract_graph),
    )
    string_hashes: dict[str, str] = build_expected_version_hashes(
        graph=string_contract_graph,
        expected_local_hashes=build_expected_local_hashes(graph=string_contract_graph),
    )

    assert (
        int_hashes["stg_orders"] != string_hashes["stg_orders"]
    ) is test_case.expected_hashes_differ


@pytest.mark.parametrize(
    "test_case",
    [
        ExpectedVersionHashesTestCase(
            description="custom materialization config changes model version hash",
            upstream_query_sql="SELECT 1 AS id",
            downstream_query_sql="SELECT 1 AS order_id",
            expected_hashes_differ=True,
        )
    ],
    ids=["custom materialization config changes model version hash"],
)
def test_given_custom_materialization_config_change_when_building_hashes_then_hashes_differ(
    test_case: ExpectedVersionHashesTestCase,
) -> None:
    first_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
        upstream_materialized="partition_tracked",
        upstream_extra_config={"config": {"partition_column": "order_date"}},
    )
    second_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
        upstream_materialized="partition_tracked",
        upstream_extra_config={"config": {"partition_column": "created_date"}},
    )

    first_hashes: dict[str, str] = build_expected_version_hashes(
        graph=first_graph,
        expected_local_hashes=build_expected_local_hashes(graph=first_graph),
    )
    second_hashes: dict[str, str] = build_expected_version_hashes(
        graph=second_graph,
        expected_local_hashes=build_expected_local_hashes(graph=second_graph),
    )

    assert (
        first_hashes["stg_orders"] != second_hashes["stg_orders"]
    ) is test_case.expected_hashes_differ


@pytest.mark.parametrize(
    "test_case",
    [
        ExpectedVersionHashesTestCase(
            description="custom materialization placeholder changes model version hash",
            upstream_query_sql="SELECT 1 AS id",
            downstream_query_sql="SELECT 1 AS order_id",
            expected_hashes_differ=True,
        )
    ],
    ids=["custom materialization placeholder changes model version hash"],
)
def test_given_custom_placeholder_change_when_building_expected_hashes_then_hashes_differ(
    test_case: ExpectedVersionHashesTestCase,
) -> None:
    first_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
        upstream_materialized="partition_tracked",
        upstream_extra_config={"placeholders": {"lower_bound": "2026-01-01"}},
    )
    second_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
        upstream_materialized="partition_tracked",
        upstream_extra_config={"placeholders": {"lower_bound": "2026-02-01"}},
    )

    first_hashes: dict[str, str] = build_expected_version_hashes(
        graph=first_graph,
        expected_local_hashes=build_expected_local_hashes(graph=first_graph),
    )
    second_hashes: dict[str, str] = build_expected_version_hashes(
        graph=second_graph,
        expected_local_hashes=build_expected_local_hashes(graph=second_graph),
    )

    assert (
        first_hashes["stg_orders"] != second_hashes["stg_orders"]
    ) is test_case.expected_hashes_differ


@pytest.mark.parametrize(
    "test_case",
    [
        ExpectedVersionHashesTestCase(
            description="pre and post hooks change model version hash",
            upstream_query_sql="SELECT 1 AS id",
            downstream_query_sql="SELECT 1 AS order_id",
            expected_hashes_differ=True,
        )
    ],
    ids=["pre and post hooks change model version hash"],
)
def test_given_hook_change_when_building_expected_hashes_then_hashes_differ(
    test_case: ExpectedVersionHashesTestCase,
) -> None:
    first_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
        upstream_extra_config={
            "pre_hooks": [SqlHookEntry(statement="SELECT 1")],
            "post_hooks": [SqlHookEntry(statement="SELECT 2")],
        },
    )
    second_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
        upstream_extra_config={
            "pre_hooks": [SqlHookEntry(statement="SELECT 3")],
            "post_hooks": [SqlHookEntry(statement="SELECT 4")],
        },
    )

    first_hashes: dict[str, str] = build_expected_version_hashes(
        graph=first_graph,
        expected_local_hashes=build_expected_local_hashes(graph=first_graph),
    )
    second_hashes: dict[str, str] = build_expected_version_hashes(
        graph=second_graph,
        expected_local_hashes=build_expected_local_hashes(graph=second_graph),
    )

    assert (
        first_hashes["stg_orders"] != second_hashes["stg_orders"]
    ) is test_case.expected_hashes_differ


@pytest.mark.parametrize(
    "test_case",
    [
        ExpectedVersionHashesTestCase(
            description="validation and backfill metadata does not change model version hash",
            upstream_query_sql="SELECT 1 AS id",
            downstream_query_sql="SELECT 1 AS order_id",
            expected_hashes_differ=False,
        )
    ],
    ids=["validation and backfill metadata does not change model version hash"],
)
def test_given_excluded_metadata_change_when_building_expected_hashes_then_hashes_match(
    test_case: ExpectedVersionHashesTestCase,
) -> None:
    baseline_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
    )
    metadata_graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql=test_case.upstream_query_sql,
        downstream_query_sql=test_case.downstream_query_sql,
        upstream_extra_config={
            "audits": ["not_null(id)"],
            "row_diff_exclude_columns": ["loaded_at"],
            "row_diff_tolerances": {"amount": {"absolute": 1}},
            "replay_on_change": "bounded-7d",
            "tags": ["nightly"],
        },
    )

    baseline_hashes: dict[str, str] = build_expected_version_hashes(
        graph=baseline_graph,
        expected_local_hashes=build_expected_local_hashes(graph=baseline_graph),
    )
    metadata_hashes: dict[str, str] = build_expected_version_hashes(
        graph=metadata_graph,
        expected_local_hashes=build_expected_local_hashes(graph=metadata_graph),
    )
    metadata_jsons: dict[str, str] = build_model_fingerprint_metadata_jsons(graph=metadata_graph)

    assert (
        baseline_hashes["stg_orders"] != metadata_hashes["stg_orders"]
    ) is test_case.expected_hashes_differ
    assert "replay_on_change" not in metadata_jsons["stg_orders"]
    assert "replay_on_change" not in metadata_jsons["stg_orders"]
    assert "row_diff" not in metadata_jsons["stg_orders"]
    assert "tags" not in metadata_jsons["stg_orders"]


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
        StaleRequiredUpstreamClosureTestCase(
            description="finds stale required upstreams for selected downstream",
            selected_model_names=("fact_orders",),
            stale_model_names=("stg_orders", "fact_orders"),
            expected_stale_upstream_names=("stg_orders",),
        )
    ],
    ids=["finds stale required upstreams for selected downstream"],
)
def test_given_selected_downstream_when_building_closure_then_it_returns_stale_ancestors(
    test_case: StaleRequiredUpstreamClosureTestCase,
) -> None:
    graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql="SELECT 1 AS id",
        downstream_query_sql="SELECT id FROM stg_orders",
    )

    stale_upstream_names: tuple[str, ...] = build_stale_required_upstream_closure(
        graph=graph,
        selected_model_names=test_case.selected_model_names,
        stale_model_names=test_case.stale_model_names,
    )

    assert stale_upstream_names == test_case.expected_stale_upstream_names


@pytest.mark.parametrize(
    "test_case",
    VIRTUAL_MODEL_SELECTION_TEST_CASES,
    ids=[case.description for case in VIRTUAL_MODEL_SELECTION_TEST_CASES],
)
def test_given_virtual_selectors_when_resolving_selection_then_it_returns_coherent_scope(
    test_case: VirtualModelSelectionTestCase,
) -> None:
    graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql="SELECT 1 AS id",
        downstream_query_sql="SELECT id FROM stg_orders",
        downstream_depends_on_dim_customers=test_case.downstream_depends_on_dim_customers,
    )

    selection: tuple[str, ...] = resolve_virtual_model_selection(
        graph=graph,
        select=test_case.select,
        exclude=(),
        default_selection=test_case.default_selection,
        stale_model_names=test_case.stale_model_names,
        include_stale_upstreams=test_case.include_stale_upstreams,
        changes_only=test_case.changes_only,
    )

    assert selection == test_case.expected_selection


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualModelSelectionTestCase(
            description="blocks selected downstream with stale required upstream",
            select=("fact_orders",),
            default_selection=("fact_orders", "stg_orders"),
            stale_model_names=("fact_orders", "stg_orders"),
            include_stale_upstreams=False,
            changes_only=False,
            expected_selection=("stg_orders",),
        )
    ],
    ids=["blocks selected downstream with stale required upstream"],
)
def test_given_virtual_selector_missing_stale_upstream_when_resolving_selection_then_it_raises(
    test_case: VirtualModelSelectionTestCase,
) -> None:
    graph: ProjectGraph = build_virtual_planner_test_project(
        upstream_query_sql="SELECT 1 AS id",
        downstream_query_sql="SELECT id FROM stg_orders",
    )

    with pytest.raises(PlannerInputError) as exc_info:
        resolve_virtual_model_selection(
            graph=graph,
            select=test_case.select,
            exclude=(),
            default_selection=test_case.default_selection,
            stale_model_names=test_case.stale_model_names,
            include_stale_upstreams=test_case.include_stale_upstreams,
            changes_only=test_case.changes_only,
        )

    assert exc_info.value.code == "S010"
    assert test_case.expected_selection[0] in exc_info.value.message


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
    STALE_ROOT_REASONS_TEST_CASES,
    ids=[case.description for case in STALE_ROOT_REASONS_TEST_CASES],
)
def test_given_stale_models_when_building_stale_root_reasons_then_it_classifies_roots(
    test_case: StaleRootReasonsTestCase,
) -> None:
    stale_root_reasons: dict[str, PlanReason] = build_stale_root_reasons(
        stale_model_names=test_case.stale_model_names,
        expected_local_hashes=test_case.expected_local_hashes,
        bound_version_hashes=test_case.bound_version_hashes,
        bound_local_hashes=test_case.bound_local_hashes,
        current_query_sqls=test_case.current_query_sqls,
        bound_previous_query_sqls=test_case.bound_previous_query_sqls,
        expected_metadata_jsons=test_case.expected_metadata_jsons,
        bound_metadata_jsons=test_case.bound_metadata_jsons,
    )

    assert stale_root_reasons == test_case.expected_stale_root_reasons


@pytest.mark.parametrize(
    "test_case",
    STALE_ROOT_CAUSES_TEST_CASES,
    ids=[case.description for case in STALE_ROOT_CAUSES_TEST_CASES],
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
        stale_root_source_causes=test_case.stale_root_source_causes,
    )

    assert stale_root_causes == test_case.expected_stale_root_causes


@pytest.mark.parametrize(
    "test_case",
    [
        StaleRootCauseReasonsTestCase(
            description="maps function source causes to function changed display reasons",
            stale_root_reasons={"fact_orders": PlanReason.QUERY_CHANGED},
            stale_root_source_causes={"fact_orders": "is_large_order"},
            expected_stale_root_cause_reasons={
                "is_large_order": PlanReason.FUNCTION_CHANGED,
            },
        )
    ],
    ids=["maps function source causes to function changed display reasons"],
)
def test_given_function_source_cause_when_building_cause_reasons_then_uses_function_reason(
    test_case: StaleRootCauseReasonsTestCase,
) -> None:
    result: dict[str, PlanReason] = build_stale_root_cause_reasons(
        stale_root_reasons=test_case.stale_root_reasons,
        stale_root_source_causes=test_case.stale_root_source_causes,
    )

    assert result == test_case.expected_stale_root_cause_reasons


@pytest.mark.parametrize(
    "test_case",
    [
        StaleRootSourceCausesTestCase(
            description="maps function metadata diff to changed function source cause",
            stale_root_reasons={"fact_orders": PlanReason.QUERY_CHANGED},
            expected_metadata_jsons={
                "fact_orders": '{"config":{},"local_function_hashes":{"is_large_order":"new"}}',
            },
            bound_metadata_jsons={
                "fact_orders": '{"config":{},"local_function_hashes":{"is_large_order":"old"}}',
            },
            expected_stale_root_source_causes={"fact_orders": "is_large_order"},
        ),
    ],
    ids=["maps function metadata diff to changed function source cause"],
)
def test_given_function_metadata_diff_when_building_source_causes_then_maps_root_to_function(
    test_case: StaleRootSourceCausesTestCase,
) -> None:
    result: dict[str, str] = build_stale_root_source_causes(
        stale_root_reasons=test_case.stale_root_reasons,
        expected_metadata_jsons=test_case.expected_metadata_jsons,
        bound_metadata_jsons=test_case.bound_metadata_jsons,
    )

    assert result == test_case.expected_stale_root_source_causes
