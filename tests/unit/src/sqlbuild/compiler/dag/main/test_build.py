from __future__ import annotations

import json
from typing import cast

import pytest

from sqlbuild.compiler.dag.main.build import build_dag_json
from tests.unit.src.sqlbuild.compiler.dag.main._test_types import (
    DagArtifactTestCase,
    DagJsonTestCase,
)
from tests.unit.src.sqlbuild.compiler.dag.main.helpers import build_dag_artifact_test_graph


@pytest.mark.parametrize(
    "test_case",
    [
        DagArtifactTestCase(
            description="builds static dag nodes edges and checks",
            expected_node_ids=(
                "source:raw_orders",
                "loader:shared_order_feed",
                "loader:raw_orders_loader",
                "seed:country_codes",
                "function:normalize_email",
                "model:orders",
            ),
            expected_edge_pairs=(
                ("function:normalize_email", "model:orders"),
                ("loader:raw_orders_loader", "source:raw_orders"),
                ("loader:shared_order_feed", "loader:raw_orders_loader"),
                ("seed:country_codes", "model:orders"),
                ("source:raw_orders", "model:orders"),
            ),
            expected_check_ids=(
                "audit:orders_audit:model:orders:order_id",
                "sql_scenario:orders_scenario",
                "sql_test:orders_test",
            ),
            expected_function_asset_key=("analytics", "normalize_email"),
            expected_source_asset_key=("raw", "orders"),
            expected_loader_asset_key=("shared_order_feed",),
        )
    ],
    ids=["builds static dag nodes edges and checks"],
)
def test_given_project_graph_when_building_dag_artifact_then_includes_assets_edges_and_checks(
    test_case: DagArtifactTestCase,
) -> None:
    payload: dict[str, object] = json.loads(
        build_dag_json(graph=build_dag_artifact_test_graph(), project_name="dag_project")
    )
    nodes: list[dict[str, object]] = payload["nodes"]
    edges: list[dict[str, object]] = payload["edges"]
    checks: list[dict[str, object]] = payload["checks"]
    nodes_by_id: dict[str, dict[str, object]] = {str(node["id"]): node for node in nodes}

    assert tuple(nodes_by_id) == test_case.expected_node_ids
    assert tuple((edge["from_id"], edge["to_id"]) for edge in edges) == (
        test_case.expected_edge_pairs
    )
    assert tuple(check["id"] for check in checks) == test_case.expected_check_ids
    assert tuple(cast(list[str], nodes_by_id["function:normalize_email"]["asset_key"])) == (
        test_case.expected_function_asset_key
    )
    assert tuple(cast(list[str], nodes_by_id["source:raw_orders"]["asset_key"])) == (
        test_case.expected_source_asset_key
    )
    assert tuple(cast(list[str], nodes_by_id["loader:shared_order_feed"]["asset_key"])) == (
        test_case.expected_loader_asset_key
    )
    assert nodes_by_id["model:orders"]["materialization_type"] == "table"
    assert nodes_by_id["loader:shared_order_feed"]["kind"] == "loader"
    assert tuple(checks[0]["checked_asset_ids"]) == ("model:orders",)


@pytest.mark.parametrize(
    "test_case",
    [
        DagJsonTestCase(
            description="serializes dag artifact as compact public json",
            expected_version=1,
            expected_project_name="dag_project",
            expected_node_count=6,
            expected_absent_fragments=(
                '"description": null',
                '"tags": []',
                '"arguments": []',
            ),
        )
    ],
    ids=["serializes dag artifact as compact public json"],
)
def test_given_dag_artifact_when_formatting_json_then_serializes_public_shape(
    test_case: DagJsonTestCase,
) -> None:
    rendered_json: str = build_dag_json(
        graph=build_dag_artifact_test_graph(),
        project_name=test_case.expected_project_name,
    )
    payload: dict[str, object] = json.loads(rendered_json)

    assert payload["version"] == test_case.expected_version
    assert payload["project_name"] == test_case.expected_project_name
    assert len(payload["nodes"]) == test_case.expected_node_count
    for fragment in test_case.expected_absent_fragments:
        assert fragment not in rendered_json
    assert "query_sql" not in json.dumps(payload)
    assert "fingerprint" not in json.dumps(payload)
