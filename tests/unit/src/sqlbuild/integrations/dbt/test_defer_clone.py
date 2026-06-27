from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.integrations.dbt.helpers.graph.core import build_dbt_combined_graph
from sqlbuild.integrations.dbt.helpers.manifest.core import build_dbt_manifest_index
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import DbtCombinedGraph
from sqlbuild.integrations.dbt.pipeline.helpers.defer_clone import (
    resolve_defer_clone_view_chain_terms,
    resolve_defer_clone_view_chain_unique_ids,
)
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtDeferCloneViewChainTermsTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    build_compiled_project_with_model_specs,
    build_manifest_data,
    build_manifest_model_node,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtDeferCloneViewChainTermsTestCase(
            description="returns exact fqn selector for skipped dbt view ancestor",
            manifest_data=build_manifest_data(
                nodes=(
                    build_manifest_model_node(
                        unique_id="model.analytics.dbt_orders",
                        package_name="analytics",
                        name="dbt_orders",
                        relation_name="analytics.dbt_orders",
                        materialized="table",
                        fqn=("analytics", "marts", "dbt_orders"),
                    ),
                    build_manifest_model_node(
                        unique_id="model.analytics.dbt_orders_view",
                        package_name="analytics",
                        name="dbt_orders_view",
                        relation_name="analytics.dbt_orders_view",
                        depends_on_nodes=("model.analytics.dbt_orders",),
                        materialized="view",
                        fqn=("analytics", "staging", "dbt_orders_view"),
                    ),
                )
            ),
            sqlbuild_model_sql_by_name={
                "downstream": 'select * from __dbt_ref("dbt_orders_view")',
            },
            selected_sqlbuild_model_names=("downstream",),
            expected_terms=("fqn:analytics.staging.dbt_orders_view",),
            expected_unique_ids=frozenset({"model.analytics.dbt_orders_view"}),
        ),
    ],
    ids=["returns exact fqn selector for skipped dbt view ancestor"],
)
def test_given_dbt_view_boundary_when_resolving_defer_clone_view_chain_then_returns_exact_terms(
    test_case: DbtDeferCloneViewChainTermsTestCase,
) -> None:
    manifest: DbtManifestIndex = build_dbt_manifest_index(raw_data=test_case.manifest_data)
    project: CompiledProject = build_compiled_project_with_model_specs(
        sql_by_model_name=test_case.sqlbuild_model_sql_by_name,
        tags_by_model_name={},
        path_by_model_name={},
    )
    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)

    result: tuple[str, ...] = resolve_defer_clone_view_chain_terms(
        graph=graph,
        manifest=manifest,
        project=project,
        selected_sqlbuild_model_names=test_case.selected_sqlbuild_model_names,
    )
    unique_ids: frozenset[str] = resolve_defer_clone_view_chain_unique_ids(
        graph=graph,
        manifest=manifest,
        project=project,
        selected_sqlbuild_model_names=test_case.selected_sqlbuild_model_names,
    )

    assert result == test_case.expected_terms
    assert unique_ids == test_case.expected_unique_ids
