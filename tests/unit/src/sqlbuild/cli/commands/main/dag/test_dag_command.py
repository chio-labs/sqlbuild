from __future__ import annotations

import json
from pathlib import Path

import pytest

from sqlbuild.cli.commands.main import dag as dag_command
from sqlbuild.cli.commands.main.dag import run_dag
from tests.unit.src.sqlbuild.cli.commands.main.dag._test_types import (
    DagCommandTestCase,
    PythonDagCommandTestCase,
)
from tests.unit.src.sqlbuild.cli.commands.main.dag.helpers import (
    NoConnectDuckDbAdapter,
    prepare_python_dag_project,
    prepare_static_dag_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DagCommandTestCase(
            description="emits static dag json without connecting",
            expected_exit_code=0,
            expected_project_name="dag_project",
            expected_node_id="model:orders",
            expected_asset_key=("analytics", "orders"),
        )
    ],
    ids=["emits static dag json without connecting"],
)
def test_given_local_project_when_running_dag_json_then_outputs_static_graph_without_connecting(
    test_case: DagCommandTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = prepare_static_dag_project(tmp_path)
    monkeypatch.setattr(
        dag_command,
        "resolve_adapter",
        lambda *args, **kwargs: NoConnectDuckDbAdapter(),
    )

    exit_code: int = run_dag(
        project_dir=project_dir,
        no_sql_validation=True,
        json_output=True,
    )
    payload: dict[str, object] = json.loads(capsys.readouterr().out)
    nodes: list[dict[str, object]] = payload["nodes"]

    assert exit_code == test_case.expected_exit_code
    assert payload["project_name"] == test_case.expected_project_name
    assert nodes[0]["id"] == test_case.expected_node_id
    assert tuple(nodes[0]["asset_key"]) == test_case.expected_asset_key


@pytest.mark.parametrize(
    "test_case",
    [
        PythonDagCommandTestCase(
            description="emits Python nodes and checks in static dag json",
            expected_exit_code=0,
            expected_task_id="task:prepare_orders",
            expected_task_tags=["daily"],
            expected_task_group="python",
            expected_task_meta={"owner": "data"},
            expected_loader_id="loader:warehouse_export",
            expected_loader_columns=[{"name": "order_id", "type": "integer"}],
            expected_asset_id="asset:orders_export",
            expected_asset_key=["asset", "orders_export"],
            expected_asset_description="Orders export artifact",
            expected_asset_group="exports",
            expected_asset_materialization_type="python_asset",
            expected_asset_columns=[{"name": "order_id", "type": "integer"}],
            expected_asset_column_lineage={
                "order_id": [{"node": "prepare_orders", "column": "order_id"}]
            },
            expected_check_id="check:check_orders_export",
            expected_check_group="exports",
            expected_edges={
                ("model:orders", "task:prepare_orders"),
                ("task:prepare_orders", "asset:orders_export"),
                ("task:prepare_orders", "loader:warehouse_export"),
                ("loader:warehouse_export", "asset:orders_export"),
                ("asset:orders_export", "check:check_orders_export"),
                ("task:prepare_orders", "check:check_orders_export"),
                ("loader:warehouse_export", "check:check_orders_export"),
                ("loader:warehouse_export", "check:check_loader_export"),
            },
            expected_check={
                "id": "check:check_orders_export",
                "kind": "python_check",
                "name": "check_orders_export",
                "checked_asset_ids": [
                    "asset:orders_export",
                    "task:prepare_orders",
                    "loader:warehouse_export",
                ],
                "path": "checks/check_orders_export.py",
                "description": "Orders export is present",
                "severity": "error",
                "tags": ["daily"],
                "group": "exports",
                "meta": {"owner": "quality"},
            },
            expected_loader_check_id="check:check_loader_export",
            expected_loader_check={
                "id": "check:check_loader_export",
                "kind": "python_check",
                "name": "check_loader_export",
                "checked_asset_ids": ["loader:warehouse_export"],
                "path": "checks/check_loader_export.py",
                "severity": "error",
                "tags": ["loader"],
            },
        )
    ],
    ids=["emits Python nodes and checks in static dag json"],
)
def test_given_python_nodes_when_running_dag_json_then_outputs_artifact_metadata(
    test_case: PythonDagCommandTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = prepare_python_dag_project(tmp_path)
    monkeypatch.setattr(
        dag_command,
        "resolve_adapter",
        lambda *args, **kwargs: NoConnectDuckDbAdapter(),
    )

    exit_code: int = run_dag(
        project_dir=project_dir,
        no_sql_validation=True,
        json_output=True,
    )
    payload: dict[str, object] = json.loads(capsys.readouterr().out)
    nodes_by_id: dict[str, dict[str, object]] = {str(node["id"]): node for node in payload["nodes"]}
    edge_pairs: set[tuple[str, str]] = {
        (str(edge["from_id"]), str(edge["to_id"])) for edge in payload["edges"]
    }
    checks_by_id: dict[str, dict[str, object]] = {
        str(check["id"]): check for check in payload["checks"]
    }

    assert exit_code == test_case.expected_exit_code
    assert nodes_by_id[test_case.expected_task_id]["kind"] == "task"
    assert nodes_by_id[test_case.expected_task_id]["tags"] == test_case.expected_task_tags
    assert nodes_by_id[test_case.expected_task_id]["group"] == test_case.expected_task_group
    assert nodes_by_id[test_case.expected_task_id]["meta"] == test_case.expected_task_meta
    loader_node: dict[str, object] = nodes_by_id[test_case.expected_loader_id]
    assert loader_node["kind"] == "loader"
    assert loader_node["columns"] == test_case.expected_loader_columns
    asset_node: dict[str, object] = nodes_by_id[test_case.expected_asset_id]
    assert asset_node["kind"] == "asset"
    assert asset_node["asset_key"] == test_case.expected_asset_key
    assert asset_node["description"] == test_case.expected_asset_description
    assert asset_node["group"] == test_case.expected_asset_group
    assert asset_node["materialization_type"] == (test_case.expected_asset_materialization_type)
    assert asset_node["columns"] == test_case.expected_asset_columns
    assert asset_node["column_lineage"] == test_case.expected_asset_column_lineage
    check_node: dict[str, object] = nodes_by_id[test_case.expected_check_id]
    assert check_node["kind"] == "check"
    assert check_node["group"] == test_case.expected_check_group
    assert test_case.expected_edges.issubset(edge_pairs)
    assert checks_by_id[test_case.expected_check_id] == test_case.expected_check
    assert checks_by_id[test_case.expected_loader_check_id] == test_case.expected_loader_check
