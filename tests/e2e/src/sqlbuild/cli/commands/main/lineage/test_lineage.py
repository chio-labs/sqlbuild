from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.lineage._test_types import (
    ColumnLineageCacheCliTestCase,
    LineageCacheCliTestCase,
    LineageCliTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.lineage.helpers import (
    lineage_node_ids,
    prepare_lineage_cache_project,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_waffle_shop,
    run_sqb,
)

_LINEAGE_CACHE_RELATIVE_PATH: Path = Path("target/cache/lineage/v1/structural-graph.sqlite3")


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


@pytest.mark.parametrize(
    "test_case",
    (
        LineageCacheCliTestCase(
            description="unchanged project reuses structural lineage cache",
            command=("lineage", "fact_orders", "--format", "json"),
            expected_node_id="model:stg_orders",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_unchanged_project_when_lineage_runs_twice_then_reuses_structural_cache(
    test_case: LineageCacheCliTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_lineage_cache_project(tmp_path=tmp_path)

    first: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )
    assert first.returncode == 0, first.stdout + first.stderr
    cache_path: Path = project_dir / _LINEAGE_CACHE_RELATIVE_PATH
    first_modified_ns: int = cache_path.stat().st_mtime_ns
    second: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert second.returncode == 0, second.stdout + second.stderr
    assert json.loads(first.stdout) == json.loads(second.stdout)
    assert test_case.expected_node_id in lineage_node_ids(payload=json.loads(second.stdout))
    assert cache_path.stat().st_mtime_ns == first_modified_ns


@pytest.mark.parametrize(
    "test_case",
    (
        LineageCacheCliTestCase(
            description="authored dependency change invalidates structural lineage cache",
            command=("lineage", "fact_orders", "--format", "json"),
            expected_node_id="model:stg_customers",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_authored_dependency_change_when_lineage_runs_then_rebuilds_structural_cache(
    test_case: LineageCacheCliTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_lineage_cache_project(tmp_path=tmp_path)
    first: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )
    assert first.returncode == 0, first.stdout + first.stderr
    (project_dir / "models/fact_orders.sql").write_text(
        "MODEL (materialized view);\n\n"
        'SELECT orders.order_id FROM __ref("stg_orders") AS orders\n'
        'JOIN __ref("stg_customers") AS customers USING (customer_id)\n',
        encoding="utf-8",
    )

    second: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert second.returncode == 0, second.stdout + second.stderr
    assert test_case.expected_node_id in lineage_node_ids(payload=json.loads(second.stdout))


@pytest.mark.parametrize(
    "test_case",
    (
        LineageCacheCliTestCase(
            description="corrupt structural cache falls back to graph rebuild",
            command=("lineage", "fact_orders", "--format", "json"),
            expected_node_id="model:stg_orders",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_corrupt_structural_cache_when_lineage_runs_then_rebuilds_safely(
    test_case: LineageCacheCliTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_lineage_cache_project(tmp_path=tmp_path)
    first: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )
    assert first.returncode == 0, first.stdout + first.stderr
    cache_path: Path = project_dir / _LINEAGE_CACHE_RELATIVE_PATH
    cache_path.write_bytes(b"not a sqlite database")

    second: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert second.returncode == 0, second.stdout + second.stderr
    assert test_case.expected_node_id in lineage_node_ids(payload=json.loads(second.stdout))
    assert cache_path.read_bytes().startswith(b"SQLite format 3")


@pytest.mark.parametrize(
    "test_case",
    (
        ColumnLineageCacheCliTestCase(
            description="column target retains analyzed lineage path",
            command=("lineage", "fact_orders.order_id", "--format", "json"),
            expected_source_resource="stg_orders",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_column_target_when_lineage_runs_then_bypasses_structural_cache(
    test_case: ColumnLineageCacheCliTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_lineage_cache_project(tmp_path=tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload: dict[str, object] = json.loads(result.stdout)
    trace: list[dict[str, object]] = payload["trace"]  # type: ignore[assignment]
    source: dict[str, object] = trace[0]["source"]  # type: ignore[assignment]
    assert source["resource_name"] == test_case.expected_source_resource
    assert not (project_dir / _LINEAGE_CACHE_RELATIVE_PATH).exists()
