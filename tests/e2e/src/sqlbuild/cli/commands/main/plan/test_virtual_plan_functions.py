from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.plan._test_types import (
    VirtualPlanE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_virtual_plan_repo_files,
    seed_matching_virtual_refs,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPlanE2ETestCase(
            description="virtual plan shows function-driven query changed root",
            seed_matching_refs=True,
            command=("--no-color", "plan", "--changes-only"),
            expected_fragments=(
                "Plan ready  3 selected",
                "stale roots: 1",
                "stale root set: fact_orders",
                "stale models: 2",
                "stale model set: fact_orders, orders_rollup",
                "Changed functions (1)",
                "is_large_order",
                "Query changed (1)",
                "fact_orders",
                "Upstream changed (1)",
                "orders_rollup",
                "cause: is_large_order (function changed)",
            ),
            unexpected_fragments=("cause: fact_orders", "stg_orders", "First run"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_plan_with_function_change_when_running_cli_then_it_marks_dependents_stale(
    test_case: VirtualPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    fact_orders_sql: str = (
        'MODEL ();\n\nSELECT __udf("is_large_order")(id) AS id FROM __ref("stg_orders")\n'
    )
    orders_rollup_sql: str = (
        'MODEL ();\n\nSELECT COUNT(*) AS order_count FROM __ref("fact_orders")\n'
    )
    baseline_function_sql: str = (
        "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, replay_on_change full);\n\n"
        "amount > 9\n"
    )
    current_function_sql: str = (
        "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, replay_on_change full);\n\n"
        "amount > 5\n"
    )
    baseline_project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_function_baseline",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id")
        | {
            "models/fact_orders.sql": fact_orders_sql,
            "models/orders_rollup.sql": orders_rollup_sql,
            "functions/sql/is_large_order.sql": baseline_function_sql,
        },
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_function_current",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id")
        | {
            "models/fact_orders.sql": fact_orders_sql,
            "models/orders_rollup.sql": orders_rollup_sql,
            "functions/sql/is_large_order.sql": current_function_sql,
        },
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "CREATE SCHEMA IF NOT EXISTS dev; "
            "CREATE TABLE IF NOT EXISTS dev.stg_orders AS SELECT 1 AS id"
        ),
    )
    seed_matching_virtual_refs(
        project_dir=project_dir,
        source_project_dir=baseline_project_dir,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr
    output: str = result.stdout
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in output, output
    for fragment in test_case.unexpected_fragments:
        assert fragment not in output, output


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPlanE2ETestCase(
            description="virtual plan after build shows changed function diff",
            seed_matching_refs=False,
            command=("--no-color", "plan", "--changes-only"),
            expected_fragments=(
                "Changed functions (1)",
                "is_large_order",
                "policy: replay_on_change=full",
                "query diff:",
                "--- previous",
                "+++ current",
                "-amount > 9",
                "+amount > 5",
                "Upstream changed (1)",
                "orders_rollup",
                "cause: is_large_order (function changed)",
            ),
            unexpected_fragments=("reason: first run", "cause: fact_orders"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_build_then_function_change_when_running_plan_then_it_shows_function_diff(
    test_case: VirtualPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    initial_function_sql: str = (
        "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, replay_on_change full);\n\n"
        "amount > 9\n"
    )
    changed_function_sql: str = (
        "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, replay_on_change full);\n\n"
        "amount > 5\n"
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_function_diff_project",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id")
        | {
            "models/fact_orders.sql": (
                'MODEL ();\n\nSELECT __udf("is_large_order")(id) AS id FROM __ref("stg_orders")\n'
            ),
            "models/orders_rollup.sql": (
                'MODEL ();\n\nSELECT COUNT(*) AS order_count FROM __ref("fact_orders")\n'
            ),
            "functions/sql/is_large_order.sql": initial_function_sql,
        },
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stderr
    (project_dir / "functions" / "sql" / "is_large_order.sql").write_text(
        changed_function_sql,
        encoding="utf-8",
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr
    output: str = result.stdout
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in output, output
    for fragment in test_case.unexpected_fragments:
        assert fragment not in output, output
