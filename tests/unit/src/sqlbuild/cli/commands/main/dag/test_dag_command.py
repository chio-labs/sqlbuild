from __future__ import annotations

import json
from pathlib import Path

import pytest

from sqlbuild.cli.commands.main import dag as dag_command
from sqlbuild.cli.commands.main.dag import run_dag
from tests.unit.src.sqlbuild.cli.commands.main.dag._test_types import DagCommandTestCase
from tests.unit.src.sqlbuild.cli.commands.main.dag.helpers import (
    NoConnectDuckDbAdapter,
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
