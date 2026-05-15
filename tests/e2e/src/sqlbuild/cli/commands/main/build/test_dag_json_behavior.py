"""E2E tests for dag --json behavior."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    DagJsonBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import prepare_waffle_shop, run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        DagJsonBuildE2ETestCase(
            description="dag json reports static graph without warehouse planning",
            command=("dag", "--json"),
            expected_exit_code=0,
            expected_project_name="waffle_shop",
            expected_node_ids=(
                "source:raw_orders",
                "seed:waffle_types",
                "function:is_completed_order",
                "model:fact_orders",
            ),
            expected_edge_pairs=(
                ("source:raw_orders", "model:stg_orders"),
                ("seed:waffle_types", "model:fact_orders"),
                ("function:is_completed_order", "model:fact_orders"),
            ),
            expected_check_ids=(
                "sql_test:test_fact_orders",
                "audit:not_null:model:fact_orders:order_id",
                "sql_scenario:daily_revenue_minimal",
            ),
            expected_absent_fragments=(
                '"description": null',
                '"tags": []',
                '"arguments": []',
            ),
        )
    ],
    ids=["dag json reports static graph without warehouse planning"],
)
def test_given_waffle_shop_when_running_dag_json_then_it_reports_static_graph(
    test_case: DagJsonBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)
    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    payload: dict[str, object] = json.loads(result.stdout)
    nodes: list[dict[str, object]] = payload["nodes"]
    edges: list[dict[str, object]] = payload["edges"]
    checks: list[dict[str, object]] = payload["checks"]
    nodes_by_id: dict[str, dict[str, object]] = {str(node["id"]): node for node in nodes}
    edge_pairs: set[tuple[str, str]] = {
        (str(edge["from_id"]), str(edge["to_id"])) for edge in edges
    }
    check_ids: set[str] = {str(check["id"]) for check in checks}

    assert payload["project_name"] == test_case.expected_project_name
    for node_id in test_case.expected_node_ids:
        assert node_id in nodes_by_id
    for edge_pair in test_case.expected_edge_pairs:
        assert edge_pair in edge_pairs
    for check_id in test_case.expected_check_ids:
        assert check_id in check_ids
    assert nodes_by_id["model:fact_orders"]["asset_key"] == ["main", "fact_orders"]
    assert nodes_by_id["function:is_completed_order"]["asset_key"] == [
        "main",
        "is_completed_order",
    ]
    for fragment in test_case.expected_absent_fragments:
        assert fragment not in result.stdout
    assert "query_sql" not in result.stdout
    assert "action" not in result.stdout
