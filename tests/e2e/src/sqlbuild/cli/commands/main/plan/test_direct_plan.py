from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.plan._test_types import (
    DirectPlanE2ETestCase,
    DirectPlanJsonE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    prepare_python_lifecycle_plan_project,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    query_duckdb,
    run_sqb,
    table_exists,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPlanE2ETestCase(
            description="standard plan shows config-only change without query diff",
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
    ids=["standard plan shows config-only change without query diff"],
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
        command=("--no-color", "build", "--force"),
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
            description="standard changes-only plan prunes unchanged selected model",
            expected_fragments=("Plan ready (0 selected)",),
            unexpected_fragments=("Normal (1)", "orders"),
        )
    ],
    ids=["standard changes-only plan prunes unchanged selected model"],
)
def test_given_built_direct_project_when_planning_changes_only_then_selects_no_unchanged_models(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_changes_only_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS order_id\n",
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr

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
            description="standard changes-only explicit select prunes unchanged selected model",
            expected_fragments=("Plan ready (0 selected)",),
            unexpected_fragments=("Models (1 standard run)", "orders"),
        )
    ],
    ids=["standard changes-only explicit select prunes unchanged selected model"],
)
def test_given_built_direct_project_when_planning_selected_changes_only_then_prunes_model(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_selected_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_changes_only_selected_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS order_id\n",
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--select", "orders"),
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
            description="direct force explicit select keeps unchanged selected model",
            expected_fragments=(
                "Plan ready (1 selected)",
                "Models (1 standard run)",
                "orders",
            ),
            unexpected_fragments=("Plan ready (0 selected)",),
        )
    ],
    ids=["direct force explicit select keeps unchanged selected model"],
)
def test_given_built_direct_project_when_planning_selected_with_force_then_keeps_model(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_selected_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_selected_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS order_id\n",
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--select", "orders", "--force"),
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
            description="standard changes-only plan keeps changed selected model",
            expected_fragments=(
                "Plan ready (1 selected)",
                "Query changed (1)",
                "orders",
                "query diff:",
            ),
            unexpected_fragments=("Plan ready (0 selected)",),
        )
    ],
    ids=["standard changes-only plan keeps changed selected model"],
)
def test_given_direct_query_change_when_planning_changes_only_then_selects_changed_model(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_changed_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_changes_only_changed_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS order_id\n",
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--force"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    (project_dir / "models" / "orders.sql").write_text(
        "MODEL (materialized table);\n\nSELECT 2 AS order_id\n",
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
            description="standard changes-only advances selected downstream by default",
            expected_fragments=(
                "Plan ready (2 selected)",
                "Query changed (1)",
                "stg_orders",
                "fact_orders",
            ),
            unexpected_fragments=("Plan ready (1 selected)",),
        )
    ],
    ids=["standard changes-only query change advances selected downstream by default"],
)
def test_given_upstream_query_change_when_planning_changes_only_then_keeps_downstream_forward_run(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_forward_cascade_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_changes_only_forward_cascade_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "models/stg_orders.sql": (
                "MODEL (materialized table);\n\nSELECT 1 AS order_id, 100 AS amount_cents\n"
            ),
            "models/fact_orders.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT order_id, amount_cents FROM __ref("stg_orders")\n'
            ),
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL (materialized table);\n\nSELECT 1 AS order_id, 125 AS amount_cents\n",
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
            description="standard changes-only retains downstream stale state outside scoped build",
            expected_fragments=(
                "Plan ready (1 selected)",
                "fact_orders",
            ),
            unexpected_fragments=("Plan ready (0 selected)",),
        )
    ],
    ids=["standard changes-only retains downstream stale state outside scoped build"],
)
def test_given_scoped_upstream_changes_only_build_when_planning_later_then_downstream_remains_stale(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_remaining_stale_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_changes_only_remaining_stale_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "models/stg_orders.sql": (
                "MODEL (materialized table);\n\nSELECT 1 AS order_id, 100 AS amount_cents\n"
            ),
            "models/fact_orders.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT order_id, amount_cents FROM __ref("stg_orders")\n'
            ),
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL (materialized table);\n\nSELECT 1 AS order_id, 125 AS amount_cents\n",
        encoding="utf-8",
    )

    scoped_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "stg_orders"),
        project_dir=project_dir,
    )
    assert scoped_build_result.returncode == 0, (
        scoped_build_result.stdout + scoped_build_result.stderr
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
            description="standard changes-only plan keeps config-only changed selected model",
            expected_fragments=(
                "Plan ready (1 selected)",
                "Config changed (1)",
                "orders",
                "config diff:",
            ),
            unexpected_fragments=("Plan ready (0 selected)", "Query changed"),
        )
    ],
    ids=["standard changes-only plan keeps config-only changed selected model"],
)
def test_given_direct_config_change_when_planning_changes_only_then_selects_changed_model(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_config_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_changes_only_config_plan"\n'
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
            description="standard changes-only plan keeps function and downstream model",
            expected_fragments=(
                "Plan ready (2 selected)",
                "Changed functions (1)",
                "is_large_order",
                "Upstream changed (1)",
                "fact_orders",
            ),
            unexpected_fragments=("Plan ready (0 selected)",),
        )
    ],
    ids=["standard changes-only plan keeps function and downstream model"],
)
def test_given_direct_function_change_when_planning_changes_only_then_selects_dependent_model(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_function_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_changes_only_function_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "functions/sql/is_large_order.sql": (
                "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, "
                "replay_on_change full);\n\namount > 100\n"
            ),
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT __udf("is_large_order")(150) AS is_large\n'
            ),
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    (project_dir / "functions" / "sql" / "is_large_order.sql").write_text(
        "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, "
        "replay_on_change full);\n\namount >= 100\n",
        encoding="utf-8",
    )

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--select", "+fact_orders"),
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
            description="standard changes-only plan keeps schema changed model",
            expected_fragments=(
                "Plan ready (1 selected)",
                "Schema changed (1)",
                "orders",
            ),
            unexpected_fragments=("Plan ready (0 selected)",),
        )
    ],
    ids=["standard changes-only plan keeps schema changed model"],
)
def test_given_direct_schema_change_when_planning_changes_only_then_selects_changed_model(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_schema_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_changes_only_schema_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "models/orders.sql": (
                "MODEL (\n"
                "  materialized incremental,\n"
                "  incremental_strategy delete_insert,\n"
                "  cursor order_id,\n"
                "  cursor_type integer,\n"
                "  unique_key order_id,\n"
                "  on_schema_change append_new_columns,\n"
                "  replay_on_change full,\n"
                "  columns (\n"
                "    order_id (type INTEGER),\n"
                "  ),\n"
                ");\n\n"
                "SELECT 1 AS order_id\n"
            ),
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    (project_dir / "models" / "orders.sql").write_text(
        "MODEL (\n"
        "  materialized incremental,\n"
        "  incremental_strategy delete_insert,\n"
        "  cursor order_id,\n"
        "  cursor_type integer,\n"
        "  unique_key order_id,\n"
        "  on_schema_change append_new_columns,\n"
        "  replay_on_change full,\n"
        "  columns (\n"
        "    order_id (type INTEGER),\n"
        "    status_rank (type INTEGER),\n"
        "  ),\n"
        ");\n\n"
        "SELECT 1 AS order_id\n",
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
            description="standard changes-only plan prunes tests and audits with unchanged target",
            expected_fragments=("Plan ready (0 selected)",),
            unexpected_fragments=("Audits", "Tests", "test_orders", "not_null"),
        )
    ],
    ids=["standard changes-only plan prunes tests and audits with unchanged target"],
)
def test_given_unchanged_direct_model_when_planning_changes_only_then_prunes_tests_and_audits(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_tests_audits_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_changes_only_tests_audits_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "models/orders.sql": (
                "MODEL (\n"
                "  materialized table,\n"
                "  columns (order_id (audits [not_null])),\n"
                ");\n\n"
                "SELECT 1 AS order_id\n"
            ),
            "tests/unit/test_orders.sql": (
                "TEST();\n\n"
                "WITH\n"
                "__ref__orders AS (SELECT 1 AS order_id),\n"
                "__expected__orders AS (SELECT 1 AS order_id)\n"
                "SELECT 1\n"
            ),
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr

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
        DirectPlanJsonE2ETestCase(
            description="standard changes-only JSON plan reports zero selected work",
            expected_selected_count=0,
            expected_model_count=0,
            expected_function_count=0,
        )
    ],
    ids=["standard changes-only JSON plan reports zero selected work"],
)
def test_given_built_direct_project_when_planning_changes_only_json_then_selected_count_is_zero(
    test_case: DirectPlanJsonE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_json_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_changes_only_json_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS order_id\n",
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--json"),
        project_dir=project_dir,
    )

    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    payload: dict[str, object] = json.loads(plan_result.stdout)
    assert payload["selected_count"] == test_case.expected_selected_count
    assert len(payload["models"]) == test_case.expected_model_count
    assert len(payload["functions"]) == test_case.expected_function_count


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPlanE2ETestCase(
            description="standard changes-only observes freshness written by normal build",
            expected_fragments=(
                "Plan ready (0 selected)",
                "Source freshness",
                "observed: 1",
                "changed: 0",
                "unchanged: 1",
                "unchanged set: raw_orders",
            ),
            unexpected_fragments=("source-stale models: orders",),
        )
    ],
    ids=["standard changes-only plan reads normal-build source freshness state"],
)
def test_given_observable_source_freshness_when_planning_changes_only_then_reads_build_state(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_source_freshness_plan_read_only",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_changes_only_source_freshness_plan_read_only"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    expression: SELECT 1 AS order_id\n"
                "    freshness:\n"
                "      strategy: sql\n"
                "      type: integer\n"
                "      query: SELECT 1 AS data_version\n"
            ),
            "models/orders.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_orders")\n'
            ),
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan"),
        project_dir=project_dir,
    )

    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in plan_result.stdout, plan_result.stdout
    assert table_exists(
        db_path=project_dir / "warehouse.duckdb",
        table_name="_sqlbuild_source_freshness",
    )

    json_plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("plan", "--json"),
        project_dir=project_dir,
    )

    assert json_plan_result.returncode == 0, json_plan_result.stdout + json_plan_result.stderr
    payload: dict[str, Any] = json.loads(json_plan_result.stdout)
    source_metadata: dict[str, Any] = payload["metadata"]["standard_source_freshness"]
    assert source_metadata["observed_source_names"] == ["raw_orders"]
    assert source_metadata["changed_source_names"] == []
    assert source_metadata["unchanged_source_names"] == ["raw_orders"]
    assert source_metadata["unknown_source_names"] == []
    assert source_metadata["stale_model_names"] == []


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPlanE2ETestCase(
            description=(
                "standard changes-only plan respects timestamp source freshness lag tolerance"
            ),
            expected_fragments=(
                "Plan ready (0 selected)",
                "Source freshness",
                "changed: 0",
                "unchanged: 1",
                "unchanged set: raw_orders",
            ),
        )
    ],
    ids=["standard changes-only plan respects timestamp source freshness lag tolerance"],
)
def test_given_timestamp_lag_tolerance_when_planning_changes_only_then_skips_within_tolerance(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    source_yml: str = (
        "sources:\n"
        "  - name: raw_orders\n"
        "    expression: SELECT 1 AS order_id\n"
        "    freshness:\n"
        "      strategy: sql\n"
        "      type: timestamp\n"
        "      lag_tolerance: 10m\n"
        "      query: SELECT CAST('{data_version}' AS TIMESTAMP) AS data_version\n"
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_plan_source_freshness_lag_tolerance",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_plan_source_freshness_lag_tolerance"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "sources/raw.yml": source_yml.format(data_version="2026-01-01T12:00:00"),
            "models/orders.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_orders")\n'
            ),
        },
    )
    initial_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert initial_build_result.returncode == 0, (
        initial_build_result.stdout + initial_build_result.stderr
    )
    baseline_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert baseline_result.returncode == 0, baseline_result.stdout + baseline_result.stderr

    (project_dir / "sources" / "raw.yml").write_text(
        source_yml.format(data_version="2026-01-01T12:05:00"), encoding="utf-8"
    )
    within_tolerance_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan"), project_dir=project_dir
    )

    assert within_tolerance_result.returncode == 0, (
        within_tolerance_result.stdout + within_tolerance_result.stderr
    )
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in within_tolerance_result.stdout, within_tolerance_result.stdout
    for fragment in test_case.unexpected_fragments:
        assert fragment not in within_tolerance_result.stdout, within_tolerance_result.stdout

    json_plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("plan", "--json"), project_dir=project_dir
    )
    assert json_plan_result.returncode == 0, json_plan_result.stdout + json_plan_result.stderr
    payload: dict[str, Any] = json.loads(json_plan_result.stdout)
    source_metadata: dict[str, Any] = payload["metadata"]["standard_source_freshness"]
    assert source_metadata["changed_source_names"] == []
    assert source_metadata["unchanged_source_names"] == ["raw_orders"]
    assert source_metadata["stale_model_names"] == []

    (project_dir / "sources" / "raw.yml").write_text(
        source_yml.format(data_version="2026-01-01T12:11:00"), encoding="utf-8"
    )
    beyond_tolerance_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan"), project_dir=project_dir
    )

    assert beyond_tolerance_result.returncode == 0, (
        beyond_tolerance_result.stdout + beyond_tolerance_result.stderr
    )
    assert "Plan ready (1 selected)" in beyond_tolerance_result.stdout
    assert "orders" in beyond_tolerance_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPlanE2ETestCase(
            description="standard source freshness skips view downstream when unchanged",
            expected_fragments=(
                "Plan ready (0 selected)",
                "Source freshness",
                "changed: 0",
                "unchanged: 1",
                "unchanged set: raw_orders",
            ),
            unexpected_fragments=("source-stale models: fact_orders, stg_orders",),
        )
    ],
    ids=["standard source freshness skips view downstream when unchanged"],
)
def test_given_source_freshness_view_chain_when_planning_changes_only_then_skips_downstream(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="standard_source_freshness_view_chain_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "standard_source_freshness_view_chain_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    expression: SELECT 1 AS order_id\n"
                "    freshness:\n"
                "      strategy: sql\n"
                "      type: integer\n"
                "      query: SELECT 1 AS data_version\n"
            ),
            "models/stg_orders.sql": (
                'MODEL (materialized view);\n\nSELECT * FROM __source("raw_orders")\n'
            ),
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __ref("stg_orders")\n'
            ),
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan"),
        project_dir=project_dir,
    )

    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in plan_result.stdout, plan_result.stdout
    for fragment in test_case.unexpected_fragments:
        assert fragment not in plan_result.stdout, plan_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPlanE2ETestCase(
            description="direct unknown source freshness conservatively keeps downstream",
            expected_fragments=(
                "Plan ready (1 selected)",
                "Source freshness",
                "unknown: 1",
                "unknown set: raw_orders",
                "source-stale models: orders",
                "orders",
            ),
            unexpected_fragments=("Plan ready (0 selected)",),
        )
    ],
    ids=["direct unknown source freshness conservatively keeps downstream"],
)
def test_given_unknown_source_freshness_when_planning_changes_only_then_keeps_downstream(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_unknown_source_freshness_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_unknown_source_freshness_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "sources/raw.yml": (
                "sources:\n  - name: raw_orders\n    expression: SELECT 1 AS order_id\n"
            ),
            "models/orders.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_orders")\n'
            ),
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan"),
        project_dir=project_dir,
    )

    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in plan_result.stdout, plan_result.stdout
    for fragment in test_case.unexpected_fragments:
        assert fragment not in plan_result.stdout, plan_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPlanE2ETestCase(
            description="run_despite_unchanged duration keeps recent rolling table and downstream",
            expected_fragments=(
                "Plan ready (2 selected)",
                "Runs despite unchanged (1)",
                "rolling_orders",
                "run_despite_unchanged: 30d",
                "newest source data age:",
                "Upstream changed (1)",
                "orders_mart",
                "cause: rolling_orders ran despite unchanged inputs",
            ),
            unexpected_fragments=("Plan ready (0 selected)",),
        )
    ],
    ids=["run_despite_unchanged duration keeps recent rolling table and downstream"],
)
def test_given_recent_source_data_when_planning_changes_only_then_runs_despite_unchanged(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_run_despite_unchanged_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_run_despite_unchanged_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    expression: SELECT 1 AS order_id\n"
                "    freshness:\n"
                "      strategy: sql\n"
                "      type: timestamp\n"
                "      query: SELECT CURRENT_TIMESTAMP AS data_version\n"
                "      lag_tolerance: 30d\n"
            ),
            "models/rolling_orders.sql": (
                "MODEL (materialized table, run_despite_unchanged 30d);\n\n"
                'SELECT order_id, CURRENT_TIMESTAMP AS refreshed_at FROM __source("raw_orders")\n'
            ),
            "models/orders_mart.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT order_id, refreshed_at FROM __ref("rolling_orders")\n'
            ),
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan"),
        project_dir=project_dir,
    )

    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in plan_result.stdout, plan_result.stdout
    for fragment in test_case.unexpected_fragments:
        assert fragment not in plan_result.stdout, plan_result.stdout

    json_plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("plan", "--json"),
        project_dir=project_dir,
    )
    assert json_plan_result.returncode == 0, json_plan_result.stdout + json_plan_result.stderr
    payload: dict[str, Any] = json.loads(json_plan_result.stdout)
    models: dict[str, dict[str, Any]] = {str(model["name"]): model for model in payload["models"]}
    decision: dict[str, Any] = models["rolling_orders"]["run_despite_unchanged"]
    assert models["rolling_orders"]["reason"] == "run_despite_unchanged"
    assert decision["mode"] == "duration"
    assert decision["duration"] == "30d"
    assert decision["newest_source_name"] == "raw_orders"
    assert isinstance(decision["newest_source_data_age_seconds"], int)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPlanE2ETestCase(
            description="expired run_despite_unchanged duration keeps unchanged table skipped",
            expected_fragments=("Plan ready (0 selected)", "Source freshness"),
            unexpected_fragments=("Runs despite unchanged", "rolling_orders"),
        )
    ],
    ids=["expired run_despite_unchanged duration skips unchanged table"],
)
def test_given_old_source_data_when_planning_changes_only_then_skips_unchanged_table(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_run_despite_unchanged_expired_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_run_despite_unchanged_expired_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    expression: SELECT 1 AS order_id\n"
                "    freshness:\n"
                "      strategy: sql\n"
                "      type: timestamp\n"
                "      query: SELECT CAST('2000-01-01 00:00:00' AS TIMESTAMP) AS data_version\n"
            ),
            "models/rolling_orders.sql": (
                "MODEL (materialized table, run_despite_unchanged 30d);\n\n"
                'SELECT order_id FROM __source("raw_orders")\n'
            ),
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan"),
        project_dir=project_dir,
    )

    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in plan_result.stdout, plan_result.stdout
    for fragment in test_case.unexpected_fragments:
        assert fragment not in plan_result.stdout, plan_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPlanE2ETestCase(
            description="run_despite_unchanged duration fails without timestamp source freshness",
            expected_fragments=(
                "run_despite_unchanged = 30d",
                "cannot determine upstream source freshness age",
                "Configure timestamp source freshness",
            ),
            unexpected_fragments=("Plan ready",),
        )
    ],
    ids=["run_despite_unchanged duration fails without timestamp source freshness"],
)
def test_given_duration_without_source_freshness_when_planning_changes_only_then_fails(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_run_despite_unchanged_missing_freshness_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_run_despite_unchanged_missing_freshness_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "sources/raw.yml": (
                "sources:\n  - name: raw_orders\n    expression: SELECT 1 AS order_id\n"
            ),
            "models/rolling_orders.sql": (
                "MODEL (materialized table, run_despite_unchanged 30d);\n\n"
                'SELECT order_id FROM __source("raw_orders")\n'
            ),
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--force"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan"),
        project_dir=project_dir,
    )
    output: str = plan_result.stdout + plan_result.stderr

    assert plan_result.returncode != 0, output
    for fragment in test_case.expected_fragments:
        assert fragment in output, output
    for fragment in test_case.unexpected_fragments:
        assert fragment not in output, output


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPlanE2ETestCase(
            description="run_despite_unchanged default applies to table model",
            expected_fragments=(
                "Plan ready (1 selected)",
                "Runs despite unchanged (1)",
                "rolling_orders",
                "run_despite_unchanged: always",
            ),
            unexpected_fragments=("Plan ready (0 selected)",),
        )
    ],
    ids=["run_despite_unchanged default applies to table model"],
)
def test_given_run_despite_unchanged_default_when_planning_changes_only_then_runs_table(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_run_despite_unchanged_default_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_run_despite_unchanged_default_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[defaults]\n"
                'run_despite_unchanged = "always"\n'
            ),
            "models/rolling_orders.sql": ("MODEL (materialized table);\n\nSELECT 1 AS order_id\n"),
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan"),
        project_dir=project_dir,
    )

    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in plan_result.stdout, plan_result.stdout
    for fragment in test_case.unexpected_fragments:
        assert fragment not in plan_result.stdout, plan_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPlanE2ETestCase(
            description="path default run_despite_unchanged applies to matching table",
            expected_fragments=(
                "Plan ready (1 selected)",
                "Runs despite unchanged (1)",
                "rolling_orders",
                "run_despite_unchanged: always",
            ),
            unexpected_fragments=("Plan ready (0 selected)",),
        )
    ],
    ids=["path default run_despite_unchanged applies to matching table"],
)
def test_given_run_despite_unchanged_path_default_when_planning_then_runs_matching_table(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_run_despite_unchanged_path_default_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_run_despite_unchanged_path_default_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                '[path_defaults."rolling"]\n'
                'run_despite_unchanged = "always"\n'
            ),
            "models/rolling/rolling_orders.sql": (
                "MODEL (materialized table);\n\nSELECT 1 AS order_id\n"
            ),
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan"),
        project_dir=project_dir,
    )

    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in plan_result.stdout, plan_result.stdout
    for fragment in test_case.unexpected_fragments:
        assert fragment not in plan_result.stdout, plan_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPlanE2ETestCase(
            description="scoped run_despite_unchanged plan reports downstream remaining stale",
            expected_fragments=(
                "Plan ready (1 selected)",
                "Runs despite unchanged (1)",
                "rolling_orders",
                "Remaining stale",
                "model set: orders_mart",
            ),
            unexpected_fragments=("Plan ready (2 selected)",),
        )
    ],
    ids=["scoped run_despite_unchanged plan reports downstream remaining stale"],
)
def test_given_scoped_run_despite_unchanged_when_planning_then_reports_remaining_stale(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_run_despite_unchanged_scoped_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_run_despite_unchanged_scoped_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "models/rolling_orders.sql": (
                "MODEL (materialized table, run_despite_unchanged always);\n\n"
                "SELECT 1 AS order_id\n"
            ),
            "models/orders_mart.sql": (
                'MODEL (materialized table);\n\nSELECT order_id FROM __ref("rolling_orders")\n'
            ),
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--select", "rolling_orders"),
        project_dir=project_dir,
    )

    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in plan_result.stdout, plan_result.stdout
    for fragment in test_case.unexpected_fragments:
        assert fragment not in plan_result.stdout, plan_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPlanE2ETestCase(
            description="standard changes-only plan surfaces explicit source freshness errors",
            expected_fragments=(
                "column freshness requires a physical table source",
                "raw_orders",
            ),
        )
    ],
    ids=["standard changes-only plan surfaces explicit source freshness errors"],
)
def test_given_invalid_explicit_source_freshness_when_planning_changes_only_then_errors(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_source_freshness_plan_error",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_changes_only_source_freshness_plan_error"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    expression: SELECT 1 AS order_id, 1 AS batch_id\n"
                "    freshness:\n"
                "      strategy: column\n"
                "      type: integer\n"
                "      column: batch_id\n"
            ),
            "models/orders.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_orders")\n'
            ),
        },
    )

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan"),
        project_dir=project_dir,
    )

    assert plan_result.returncode != 0, plan_result.stdout + plan_result.stderr
    output: str = plan_result.stdout + plan_result.stderr
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in output, output


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPlanE2ETestCase(
            description="standard changes-only plan keeps downstream cascade",
            expected_fragments=(
                "Plan ready (2 selected)",
                "Query changed (1)",
                "stg_orders",
                "Upstream changed (1)",
                "fact_orders",
            ),
            unexpected_fragments=("Plan ready (0 selected)",),
        )
    ],
    ids=["standard changes-only plan keeps downstream cascade"],
)
def test_given_selected_upstream_query_change_when_planning_changes_only_then_keeps_cascade(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_cascade_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_changes_only_cascade_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "models/stg_orders.sql": (
                "MODEL ("
                "materialized incremental, incremental_strategy delete_insert, "
                "cursor order_id, cursor_type integer, unique_key order_id, "
                "replay_on_change full);\n\nSELECT 1 AS order_id\n"
            ),
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT order_id FROM __ref("stg_orders")\n'
            ),
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ("
        "materialized incremental, incremental_strategy delete_insert, "
        "cursor order_id, cursor_type integer, unique_key order_id, "
        "replay_on_change full);\n\nSELECT 2 AS order_id\n",
        encoding="utf-8",
    )

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--select", "+fact_orders"),
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
            description="direct full-refresh changes-only keeps selected model",
            expected_fragments=(
                "Plan ready (full refresh, 1 selected)",
                "Full refresh (1)",
                "1 table",
            ),
            unexpected_fragments=("Plan ready (0 selected)",),
        )
    ],
    ids=["direct full-refresh changes-only keeps selected model"],
)
def test_given_built_direct_project_when_planning_full_refresh_changes_only_then_keeps_model(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_full_refresh_changes_only_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_full_refresh_changes_only_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS order_id\n",
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--full-refresh"),
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
            description="standard plan shows selected Python lifecycle nodes",
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
    ids=["standard plan shows selected Python lifecycle nodes"],
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
            description="direct source plan warns for skipped task ingress dependency",
            expected_fragments=(
                "Plan ready (0 selected, 1 source to load)",
                "Sources to load (1)",
                "raw_orders",
                "Warnings (1)",
                "Source loader 'raw_orders' has unselected upstream task 'prepare_orders'",
                "use +source:raw_orders to refresh upstream ingress dependencies",
            ),
            unexpected_fragments=("Python ingress", "python    task      prepare_orders"),
        )
    ],
    ids=["direct source plan warns for skipped task ingress dependency"],
)
def test_given_direct_source_with_task_ingress_when_planning_without_expansion_then_warns(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_source_task_ingress_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_source_task_ingress_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "direct_source_task_ingress_plan.duckdb"\n'
            ),
            "tasks/prepare.py": (
                "from sqlbuild.tasks import task\n\n"
                "@task\n"
                "def prepare_orders(ctx):\n"
                "    return ctx.result()\n"
            ),
            "loaders/raw.py": (
                "from sqlbuild.loaders import loader\n"
                "from tasks.prepare import prepare_orders\n\n"
                "@loader(depends_on=[prepare_orders])\n"
                "def raw_orders(ctx):\n"
                "    return [{'order_id': 1}]\n"
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
            ),
        },
    )

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--select", "raw_orders"),
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
            description="direct Python task plan shows persisted identity statuses",
            expected_fragments=(
                "Python ingress (1)",
                "prepare_orders",
                "task (changed)",
                "python diff:",
                "source diff:",
                "dependency diff:",
                "-    return ctx.result(metadata={'label': order_label()})",
                "+    return ctx.result(metadata={'label': order_label(), 'version': 2})",
                "helpers.py :: tasks.helpers :: order_label",
                "-    return 'ready'",
                "+    return 'changed'",
            ),
            unexpected_fragments=("task (new)",),
        )
    ],
    ids=["direct Python task plan shows persisted identity statuses"],
)
def test_given_direct_python_task_identity_when_planning_then_reports_identity_status(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_python_identity_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_python_identity_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "direct_python_identity_plan.duckdb"\n'
            ),
            "tasks/helpers.py": ("def order_label():\n    return 'ready'\n"),
            "tasks/prepare.py": (
                "from sqlbuild.tasks import task\n"
                "from tasks.helpers import order_label\n\n"
                "@task\n"
                "def prepare_orders(ctx):\n"
                "    return ctx.result(metadata={'label': order_label()})\n"
            ),
            "loaders/raw.py": (
                "from sqlbuild.loaders import loader\n"
                "from tasks.prepare import prepare_orders\n\n"
                "@loader(depends_on=[prepare_orders])\n"
                "def raw_orders(ctx):\n"
                "    return [{'order_id': 1}]\n"
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
            ),
        },
    )

    initial_plan: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--select", "+raw_orders"),
        project_dir=project_dir,
    )
    assert initial_plan.returncode == 0, initial_plan.stdout + initial_plan.stderr
    assert "task (new)" in initial_plan.stdout

    run_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "+raw_orders"),
        project_dir=project_dir,
    )
    assert run_result.returncode == 0, run_result.stdout + run_result.stderr

    rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "direct_python_identity_plan.duckdb",
        sql=(
            "SELECT node_type, node_name, definition_b64, metadata_json_b64 "
            "FROM main._sqlbuild_fingerprints "
            "WHERE node_type IN ('task', 'loader') "
            "ORDER BY node_type, node_name"
        ),
    )
    assert [row[0:2] for row in rows] == [("loader", "raw_orders"), ("task", "prepare_orders")]
    task_row: tuple[object, ...] = rows[1]
    definition_payload: str = base64.b64decode(str(task_row[2]).encode("ascii")).decode("utf-8")
    metadata_payload: str = base64.b64decode(str(task_row[3]).encode("ascii")).decode("utf-8")
    loader_definition_payload: str = base64.b64decode(str(rows[0][2]).encode("ascii")).decode(
        "utf-8"
    )
    assert "def raw_orders(ctx):" in loader_definition_payload
    assert "def prepare_orders(ctx):" in definition_payload
    assert "def order_label():" in metadata_payload

    unchanged_plan: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--select", "+raw_orders"),
        project_dir=project_dir,
    )
    assert unchanged_plan.returncode == 0, unchanged_plan.stdout + unchanged_plan.stderr
    assert "task (unchanged)" in unchanged_plan.stdout

    (project_dir / "tasks" / "helpers.py").write_text(
        "def order_label():\n    return 'changed'\n",
        encoding="utf-8",
    )
    (project_dir / "tasks" / "prepare.py").write_text(
        "from sqlbuild.tasks import task\n"
        "from tasks.helpers import order_label\n\n"
        "@task\n"
        "def prepare_orders(ctx):\n"
        "    return ctx.result(metadata={'label': order_label(), 'version': 2})\n",
        encoding="utf-8",
    )

    changed_plan: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--select", "+raw_orders"),
        project_dir=project_dir,
    )

    assert changed_plan.returncode == 0, changed_plan.stdout + changed_plan.stderr
    output: str = changed_plan.stdout
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in output, output
    for fragment in test_case.unexpected_fragments:
        assert fragment not in output, output


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPlanE2ETestCase(
            description=(
                "changed Python identity remains display only for changes-only SQL selection"
            ),
            expected_fragments=(
                "Plan ready (0 selected",
                "Python ingress (1)",
                "prepare_orders",
                "task (changed)",
                "python diff:",
            ),
            unexpected_fragments=("Models (", "First run (", "Query changed (", "fact_orders"),
        )
    ],
    ids=["changed Python identity remains display only for changes-only SQL selection"],
)
def test_given_changed_python_identity_when_planning_changes_only_then_sql_work_is_not_selected(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_python_identity_display_only_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_python_identity_display_only_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "direct_python_identity_display_only_plan.duckdb"\n'
            ),
            "tasks/helpers.py": "def order_label():\n    return 'ready'\n",
            "tasks/prepare.py": (
                "from sqlbuild.tasks import task\n"
                "from tasks.helpers import order_label\n\n"
                "@task\n"
                "def prepare_orders(ctx):\n"
                "    return ctx.result(metadata={'label': order_label()})\n"
            ),
            "loaders/raw.py": (
                "from sqlbuild.loaders import loader\n"
                "from tasks.prepare import prepare_orders\n\n"
                "@loader(depends_on=[prepare_orders])\n"
                "def raw_orders(ctx):\n"
                "    return [{'order_id': 1}]\n"
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
            ),
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT order_id FROM __source("raw_orders")\n'
            ),
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "+fact_orders"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    (project_dir / "tasks" / "helpers.py").write_text(
        "def order_label():\n    return 'changed'\n",
        encoding="utf-8",
    )

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--select", "+fact_orders"),
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
            description="direct source plan warns for skipped asset ingress dependency",
            expected_fragments=(
                "Plan ready (0 selected, 1 source to load)",
                "Warnings (1)",
                "Source loader 'raw_orders' has unselected upstream asset 'prepare_orders'",
            ),
            unexpected_fragments=("Python ingress",),
        )
    ],
    ids=["direct source plan warns for skipped asset ingress dependency"],
)
def test_given_direct_source_with_asset_ingress_when_planning_without_expansion_then_warns(
    test_case: DirectPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_source_asset_ingress_plan",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_source_asset_ingress_plan"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "direct_source_asset_ingress_plan.duckdb"\n'
            ),
            "assets/prepare.py": (
                "from sqlbuild.assets import asset\n\n"
                "@asset\n"
                "def prepare_orders(ctx):\n"
                "    return ctx.result(materialized=True)\n"
            ),
            "loaders/raw.py": (
                "from sqlbuild.loaders import loader\n"
                "from assets.prepare import prepare_orders\n\n"
                "@loader(depends_on=[prepare_orders])\n"
                "def raw_orders(ctx):\n"
                "    return [{'order_id': 1}]\n"
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
            ),
        },
    )

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--select", "raw_orders"),
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
            description="standard plan json includes selected Python lifecycle nodes",
            expected_fragments=(
                "prepare_orders",
                "publish_prepared_orders",
                "profile_fact_orders",
                "notify_fact_orders",
            ),
        )
    ],
    ids=["standard plan json includes selected Python lifecycle nodes"],
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
        "phase": "pre_sql_ingress",
        "identity_status": "new",
    }
    assert nodes_by_name["publish_prepared_orders"] == {
        "name": "publish_prepared_orders",
        "kind": "asset",
        "phase": "pre_sql_ingress",
        "identity_status": "new",
    }
    assert nodes_by_name["profile_fact_orders"] == {
        "name": "profile_fact_orders",
        "kind": "task",
        "phase": "read_side",
        "identity_status": "new",
    }
    assert nodes_by_name["notify_fact_orders"] == {
        "name": "notify_fact_orders",
        "kind": "task",
        "phase": "read_side",
        "identity_status": "new",
    }


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPlanE2ETestCase(
            description="standard plan rejects unselected Python dependencies",
            expected_fragments=(
                "Python node 'notify_fact_orders' depends on unselected Python node "
                "'profile_fact_orders'",
            ),
        )
    ],
    ids=["standard plan rejects unselected Python dependencies"],
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
