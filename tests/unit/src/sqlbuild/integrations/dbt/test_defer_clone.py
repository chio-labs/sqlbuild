from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.integrations.dbt.helpers.graph.core import build_dbt_combined_graph
from sqlbuild.integrations.dbt.helpers.manifest.core import build_dbt_manifest_index
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import DbtCombinedGraph
from sqlbuild.integrations.dbt.pipeline.helpers.defer_clone import (
    resolve_defer_clone_unique_ids,
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
            selected_dbt_unique_ids=(),
            expected_terms=("fqn:analytics.staging.dbt_orders_view",),
            expected_unique_ids=frozenset({"model.analytics.dbt_orders_view"}),
            expected_clone_unique_ids=frozenset({"model.analytics.dbt_orders"}),
        ),
        DbtDeferCloneViewChainTermsTestCase(
            description="returns boundary and view chain for selected dbt model",
            manifest_data=build_manifest_data(
                nodes=(
                    build_manifest_model_node(
                        unique_id="model.analytics.boundary_table",
                        package_name="analytics",
                        name="boundary_table",
                        relation_name="analytics.boundary_table",
                        materialized="table",
                        fqn=("analytics", "marts", "boundary_table"),
                    ),
                    build_manifest_model_node(
                        unique_id="model.analytics.stale_view",
                        package_name="analytics",
                        name="stale_view",
                        relation_name="analytics.stale_view",
                        depends_on_nodes=("model.analytics.boundary_table",),
                        materialized="view",
                        fqn=("analytics", "marts", "stale_view"),
                    ),
                    build_manifest_model_node(
                        unique_id="model.analytics.selected_model",
                        package_name="analytics",
                        name="selected_model",
                        relation_name="analytics.selected_model",
                        depends_on_nodes=("model.analytics.stale_view",),
                        materialized="table",
                        fqn=("analytics", "staging", "selected_model"),
                    ),
                )
            ),
            sqlbuild_model_sql_by_name={},
            selected_sqlbuild_model_names=(),
            selected_dbt_unique_ids=("model.analytics.selected_model",),
            expected_terms=("fqn:analytics.marts.stale_view",),
            expected_unique_ids=frozenset({"model.analytics.stale_view"}),
            expected_clone_unique_ids=frozenset({"model.analytics.boundary_table"}),
        ),
    ],
    ids=lambda case: case.description,
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
        selected_dbt_unique_ids=test_case.selected_dbt_unique_ids,
    )
    unique_ids: frozenset[str] = resolve_defer_clone_view_chain_unique_ids(
        graph=graph,
        manifest=manifest,
        project=project,
        selected_sqlbuild_model_names=test_case.selected_sqlbuild_model_names,
        selected_dbt_unique_ids=test_case.selected_dbt_unique_ids,
    )
    clone_unique_ids: frozenset[str] = resolve_defer_clone_unique_ids(
        graph=graph,
        manifest=manifest,
        project=project,
        selected_sqlbuild_model_names=test_case.selected_sqlbuild_model_names,
        selected_dbt_unique_ids=test_case.selected_dbt_unique_ids,
        required_dbt_unique_ids=(),
    )

    assert result == test_case.expected_terms
    assert unique_ids == test_case.expected_unique_ids
    assert clone_unique_ids == test_case.expected_clone_unique_ids
