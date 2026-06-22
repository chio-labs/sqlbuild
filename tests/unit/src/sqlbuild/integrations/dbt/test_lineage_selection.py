from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.integrations.dbt.exceptions import DbtInteropArgumentError
from sqlbuild.integrations.dbt.helpers.graph.core import build_dbt_combined_graph
from sqlbuild.integrations.dbt.helpers.lineage.selection import (
    resolve_dbt_lineage_target,
    select_dbt_lineage_target,
)
from sqlbuild.integrations.dbt.helpers.manifest.core import build_dbt_manifest_index
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import DbtCombinedGraph, DbtLineageGraph
from sqlbuild.integrations.dbt.types import DbtLineageDirection
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtLineageSelectionErrorTestCase,
    DbtLineageSelectionTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    build_compiled_project_with_models,
    build_lineage_manifest_data,
    build_manifest_data,
    build_manifest_model_node,
)

LINEAGE_SELECTION_TEST_CASES: tuple[DbtLineageSelectionTestCase, ...] = (
    DbtLineageSelectionTestCase(
        description="selects upstream dbt graph from SQLBuild model",
        target="mart_orders",
        direction=DbtLineageDirection.UPSTREAM,
        depth=None,
        expected_node_ids=(
            "dbt:model:model.analytics.int_orders",
            "dbt:model:model.analytics.stg_orders",
            "dbt:source:source.analytics.raw.orders",
            "sqb:model:fact_orders",
            "sqb:model:mart_orders",
        ),
        expected_edges=(
            ("dbt:model:model.analytics.stg_orders", "dbt:model:model.analytics.int_orders"),
            ("dbt:source:source.analytics.raw.orders", "dbt:model:model.analytics.stg_orders"),
            ("dbt:model:model.analytics.int_orders", "sqb:model:fact_orders"),
            ("sqb:model:fact_orders", "sqb:model:mart_orders"),
        ),
        expected_focus_ids=("sqb:model:mart_orders",),
    ),
    DbtLineageSelectionTestCase(
        description="selects downstream SQLBuild graph from dbt unique id",
        target="model.analytics.stg_orders",
        direction=DbtLineageDirection.DOWNSTREAM,
        depth=None,
        expected_node_ids=(
            "dbt:model:model.analytics.int_orders",
            "dbt:model:model.analytics.stg_orders",
            "sqb:model:fact_orders",
            "sqb:model:mart_orders",
        ),
        expected_edges=(
            ("dbt:model:model.analytics.stg_orders", "dbt:model:model.analytics.int_orders"),
            ("dbt:model:model.analytics.int_orders", "sqb:model:fact_orders"),
            ("sqb:model:fact_orders", "sqb:model:mart_orders"),
        ),
        expected_focus_ids=("dbt:model:model.analytics.stg_orders",),
    ),
    DbtLineageSelectionTestCase(
        description="selects depth limited upstream graph from unambiguous dbt name",
        target="int_orders",
        direction=DbtLineageDirection.UPSTREAM,
        depth=1,
        expected_node_ids=(
            "dbt:model:model.analytics.int_orders",
            "dbt:model:model.analytics.stg_orders",
        ),
        expected_edges=(
            ("dbt:model:model.analytics.stg_orders", "dbt:model:model.analytics.int_orders"),
        ),
        expected_focus_ids=("dbt:model:model.analytics.int_orders",),
    ),
    DbtLineageSelectionTestCase(
        description="selects only focus node with zero depth",
        target="mart_orders",
        direction=DbtLineageDirection.UPSTREAM,
        depth=0,
        expected_node_ids=("sqb:model:mart_orders",),
        expected_edges=(),
        expected_focus_ids=("sqb:model:mart_orders",),
    ),
)

LINEAGE_SELECTION_ERROR_TEST_CASES: tuple[DbtLineageSelectionErrorTestCase, ...] = (
    DbtLineageSelectionErrorTestCase(
        description="rejects ambiguous dbt short name",
        target="orders",
        expected_error_fragment="ambiguous dbt lineage target 'orders'",
        expected_code="C330",
    ),
    DbtLineageSelectionErrorTestCase(
        description="rejects unknown target",
        target="missing_orders",
        expected_error_fragment="unknown dbt lineage target 'missing_orders'",
        expected_code="C331",
    ),
)


@pytest.mark.parametrize(
    "test_case",
    LINEAGE_SELECTION_TEST_CASES,
    ids=[case.description for case in LINEAGE_SELECTION_TEST_CASES],
)
def test_given_combined_graph_when_selecting_lineage_target_then_returns_expected_slice(
    test_case: DbtLineageSelectionTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(raw_data=build_lineage_manifest_data())
    project: CompiledProject = build_compiled_project_with_models(
        {
            "fact_orders": 'select * from __dbt_ref("int_orders")',
            "mart_orders": 'select * from __ref("fact_orders")',
        }
    )
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)

    lineage_graph: DbtLineageGraph = select_dbt_lineage_target(
        project=project,
        manifest=manifest,
        graph=graph,
        target=test_case.target,
        direction=test_case.direction,
        depth=test_case.depth,
    )

    assert tuple(node.key.stable_id for node in lineage_graph.nodes) == test_case.expected_node_ids
    assert (
        tuple(
            (upstream.stable_id, downstream.stable_id)
            for upstream, downstream in lineage_graph.edges
        )
        == test_case.expected_edges
    )
    assert tuple(key.stable_id for key in lineage_graph.focus_keys) == test_case.expected_focus_ids


@pytest.mark.parametrize(
    "test_case",
    LINEAGE_SELECTION_ERROR_TEST_CASES,
    ids=[case.description for case in LINEAGE_SELECTION_ERROR_TEST_CASES],
)
def test_given_invalid_lineage_target_when_resolving_then_raises_clear_error(
    test_case: DbtLineageSelectionErrorTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                build_manifest_model_node(
                    unique_id="model.analytics.orders",
                    package_name="analytics",
                    name="orders",
                    relation_name="analytics.orders",
                ),
                build_manifest_model_node(
                    unique_id="model.stripe.orders",
                    package_name="stripe",
                    name="orders",
                    relation_name="stripe.orders",
                ),
            )
        )
    )
    project: CompiledProject = build_compiled_project_with_models({})

    with pytest.raises(DbtInteropArgumentError) as exc_info:
        resolve_dbt_lineage_target(
            project=project,
            manifest=manifest,
            target=test_case.target,
        )

    assert test_case.expected_error_fragment in str(exc_info.value)
    assert exc_info.value.code == test_case.expected_code


@pytest.mark.parametrize(
    "test_case",
    [
        DbtLineageSelectionTestCase(
            description="prefers SQLBuild model over dbt short name collision",
            target="shared_orders",
            direction=DbtLineageDirection.UPSTREAM,
            depth=None,
            expected_node_ids=("sqb:model:shared_orders",),
            expected_edges=(),
            expected_focus_ids=("sqb:model:shared_orders",),
        )
    ],
    ids=["prefers SQLBuild model over dbt short name collision"],
)
def test_given_sqlbuild_and_dbt_name_collision_when_selecting_then_prefers_sqlbuild_model(
    test_case: DbtLineageSelectionTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=build_manifest_data(
            nodes=(
                build_manifest_model_node(
                    unique_id="model.analytics.shared_orders",
                    package_name="analytics",
                    name="shared_orders",
                    relation_name="analytics.shared_orders",
                ),
            )
        )
    )
    project: CompiledProject = build_compiled_project_with_models(
        {"shared_orders": "select 1 as order_id"}
    )
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)

    lineage_graph: DbtLineageGraph = select_dbt_lineage_target(
        project=project,
        manifest=manifest,
        graph=graph,
        target=test_case.target,
        direction=test_case.direction,
        depth=test_case.depth,
    )

    assert tuple(node.key.stable_id for node in lineage_graph.nodes) == test_case.expected_node_ids
    assert (
        tuple(
            (upstream.stable_id, downstream.stable_id)
            for upstream, downstream in lineage_graph.edges
        )
        == test_case.expected_edges
    )
    assert tuple(key.stable_id for key in lineage_graph.focus_keys) == test_case.expected_focus_ids
