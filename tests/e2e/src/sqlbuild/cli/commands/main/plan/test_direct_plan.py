from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.plan._test_types import DirectPlanE2ETestCase
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    prepare_python_lifecycle_plan_project,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPlanE2ETestCase(
            description="direct plan shows config-only change without query diff",
            expected_fragments=(
                "Plan ready (1 selected)",
                "Config changed (1)",
                "orders",
                "config diff:",
                '"materialized": "view"',
                '"materialized": "table"',
            ),
            unexpected_fragments=("Query changed", "query diff:"),
        )
    ],
    ids=["direct plan shows config-only change without query diff"],
)
def test_given_direct_project_with_config_only_change_when_planning_then_reports_config_change(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_config_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_config_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "models/orders.sql": "MODEL (materialized view);\n\nSELECT 1 AS order_id\n",
        },
    )

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    (project_dir / "models" / "orders.sql").write_text(
        "MODEL (materialized table);\n\nSELECT 1 AS order_id\n",
        encoding="utf-8",
    )

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan"),
        project_dir=project_dir,
    )

    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    output: str = plan_result.stdout
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in output, output
    for fragment in test_case.unexpected_fragments:
        assert fragment not in output, output


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPlanE2ETestCase(
            description="direct plan shows selected Python lifecycle nodes",
            expected_fragments=(
                "Plan ready (1 selected, 2 sources to load, 4 Python nodes)",
                "Python ingress (2)",
                "prepare_orders",
                "publish_prepared_orders",
                "Loaders to load (1)",
                "load_window_orders",
                "Sources to load (1)",
                "raw_orders",
                "First run (1)",
                "fact_orders",
                "Python read-side (2)",
                "profile_fact_orders",
                "notify_fact_orders",
            ),
        )
    ],
    ids=["direct plan shows selected Python lifecycle nodes"],
)
def test_given_python_lifecycle_project_when_planning_then_shows_python_sections(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_python_lifecycle_plan_project(tmp_path=tmp_path)

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "plan",
            "--select",
            "+fact_orders +notify_fact_orders",
        ),
        project_dir=project_dir,
    )

    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    output: str = plan_result.stdout
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in output, output
    assert output.index("Python ingress (2)") < output.index("Sources to load (1)")
    assert output.index("First run (1)") < output.index("Python read-side (2)")


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPlanE2ETestCase(
            description="direct plan json includes selected Python lifecycle nodes",
            expected_fragments=(
                "prepare_orders",
                "publish_prepared_orders",
                "profile_fact_orders",
                "notify_fact_orders",
            ),
        )
    ],
    ids=["direct plan json includes selected Python lifecycle nodes"],
)
def test_given_python_lifecycle_project_when_planning_json_then_includes_python_nodes(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_python_lifecycle_plan_project(tmp_path=tmp_path)

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "plan",
            "--json",
            "--select",
            "+fact_orders +notify_fact_orders",
        ),
        project_dir=project_dir,
    )

    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    payload: dict[str, object] = json.loads(plan_result.stdout)
    python_nodes: list[dict[str, Any]] = list(payload["python_nodes"])  # type: ignore[arg-type]
    assert payload["python_node_count"] == 4
    nodes_by_name: dict[str, dict[str, Any]] = {str(node["name"]): node for node in python_nodes}
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in nodes_by_name
    assert nodes_by_name["prepare_orders"] == {
        "name": "prepare_orders",
        "kind": "task",
        "region": "pre_sql_ingress",
    }
    assert nodes_by_name["publish_prepared_orders"] == {
        "name": "publish_prepared_orders",
        "kind": "asset",
        "region": "pre_sql_ingress",
    }
    assert nodes_by_name["profile_fact_orders"] == {
        "name": "profile_fact_orders",
        "kind": "task",
        "region": "sql_read_python",
    }
    assert nodes_by_name["notify_fact_orders"] == {
        "name": "notify_fact_orders",
        "kind": "task",
        "region": "sql_read_python",
    }


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPlanE2ETestCase(
            description="direct plan rejects unselected Python dependencies",
            expected_fragments=(
                "Python node 'notify_fact_orders' depends on unselected Python node "
                "'profile_fact_orders'",
            ),
        )
    ],
    ids=["direct plan rejects unselected Python dependencies"],
)
def test_given_python_lifecycle_project_when_planning_without_dependency_then_fails(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_python_lifecycle_plan_project(tmp_path=tmp_path)

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "plan",
            "--select",
            "load_window_orders fact_orders notify_fact_orders",
        ),
        project_dir=project_dir,
    )

    assert plan_result.returncode != 0, plan_result.stdout + plan_result.stderr
    output: str = plan_result.stdout + plan_result.stderr
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in output, output
