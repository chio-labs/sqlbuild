from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.integrations.dbt.helpers.graph import (
    build_dbt_combined_graph,
    expand_combined_downstream,
    expand_combined_upstream,
)
from sqlbuild.integrations.dbt.helpers.manifest import build_dbt_manifest_index
from sqlbuild.integrations.dbt.models import DbtCombinedGraph, DbtManifestIndex
from tests.unit.src.sqlbuild.integrations.dbt._test_types import DbtCombinedGraphTestCase
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    build_compiled_project_with_models,
    build_manifest_data,
    build_manifest_model_node,
    graph_edge_stable_ids,
    graph_key_from_stable_id,
    graph_key_stable_ids,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtCombinedGraphTestCase(
            description="builds dbt dbt-to-sqb and sqb-to-sqb graph",
            manifest_data=build_manifest_data(
                nodes=(
                    build_manifest_model_node(
                        unique_id="model.analytics.stg_orders",
                        package_name="analytics",
                        name="stg_orders",
                        relation_name="analytics.stg_orders",
                    ),
                    build_manifest_model_node(
                        unique_id="model.analytics.int_orders",
                        package_name="analytics",
                        name="int_orders",
                        relation_name="analytics.int_orders",
                        depends_on_nodes=("model.analytics.stg_orders",),
                    ),
                )
            ),
            sqlbuild_model_sql_by_name={
                "fact_orders": 'select * from __dbt_ref("int_orders")',
                "mart_orders": 'select * from __ref("fact_orders")',
            },
            expected_upstream_edges=(
                ("dbt:model:model.analytics.stg_orders", ()),
                (
                    "dbt:model:model.analytics.int_orders",
                    ("dbt:model:model.analytics.stg_orders",),
                ),
                ("sqb:model:fact_orders", ("dbt:model:model.analytics.int_orders",)),
                ("sqb:model:mart_orders", ("sqb:model:fact_orders",)),
            ),
            expected_downstream_from="dbt:model:model.analytics.stg_orders",
            expected_downstream_keys=(
                "dbt:model:model.analytics.int_orders",
                "sqb:model:fact_orders",
                "sqb:model:mart_orders",
            ),
            expected_upstream_from="sqb:model:mart_orders",
            expected_upstream_keys=(
                "dbt:model:model.analytics.int_orders",
                "dbt:model:model.analytics.stg_orders",
                "sqb:model:fact_orders",
            ),
        ),
    ],
    ids=["builds dbt dbt-to-sqb and sqb-to-sqb graph"],
)
def test_given_manifest_and_compiled_project_when_building_graph_then_returns_expected_edges(
    test_case: DbtCombinedGraphTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(raw_data=test_case.manifest_data)
    project: CompiledProject = build_compiled_project_with_models(
        test_case.sqlbuild_model_sql_by_name
    )

    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)

    assert graph_edge_stable_ids(graph.upstream_deps) == dict(test_case.expected_upstream_edges)
    assert (
        graph_key_stable_ids(
            expand_combined_downstream(
                graph_key_from_stable_id(test_case.expected_downstream_from),
                graph.downstream_deps,
            )
        )
        == test_case.expected_downstream_keys
    )
    assert (
        graph_key_stable_ids(
            expand_combined_upstream(
                graph_key_from_stable_id(test_case.expected_upstream_from),
                graph.upstream_deps,
            )
        )
        == test_case.expected_upstream_keys
    )
