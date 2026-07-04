from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.lineage._test_types import LineageCliTestCase
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_waffle_shop, run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        LineageCliTestCase(
            description="renders upstream fact orders lineage json without warehouse tables",
            command=("lineage", "fact_orders", "--format", "json"),
            expected_exit_code=0,
            expected_node_ids=(
                "model:fact_orders",
                "model:stg_orders",
                "model:stg_payments",
                "seed:waffle_types",
                "source:raw_orders",
                "source:raw_payments",
                "udf:is_completed_order",
                "udf:is_completed_order_py",
            ),
            expected_edge_ids=(
                "udf:is_completed_order->model:fact_orders",
                "udf:is_completed_order_py->model:fact_orders",
                "model:stg_orders->model:fact_orders",
                "seed:waffle_types->model:fact_orders",
                "model:stg_payments->model:fact_orders",
                "source:raw_orders->model:stg_orders",
                "source:raw_payments->model:stg_payments",
            ),
        ),
        LineageCliTestCase(
            description="renders path-between selector lineage as json",
            command=(
                "lineage",
                "--select",
                "fact_orders~daily_activity_rollup",
                "--format",
                "json",
            ),
            expected_exit_code=0,
            expected_node_ids=(
                "model:daily_activity_rollup",
                "model:fact_orders",
                "model:hourly_order_activity",
                "udf:is_completed_order",
                "udf:is_completed_order_py",
            ),
            expected_edge_ids=(
                "model:hourly_order_activity->model:daily_activity_rollup",
                "udf:is_completed_order->model:fact_orders",
                "udf:is_completed_order_py->model:fact_orders",
                "model:fact_orders->model:hourly_order_activity",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_lineage_command_when_running_then_outputs_expected_json_graph(
    test_case: LineageCliTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    payload: dict[str, object] = json.loads(result.stdout)
    node_ids: tuple[str, ...] = tuple(node["id"] for node in payload["nodes"])  # type: ignore[index]
    edge_ids: tuple[str, ...] = tuple(
        f"{edge['from']}->{edge['to']}"
        for edge in payload["edges"]  # type: ignore[index]
    )
    assert node_ids == test_case.expected_node_ids
    assert edge_ids == test_case.expected_edge_ids
