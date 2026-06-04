from __future__ import annotations

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
    run_sqb,
    table_exists,
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
            description="direct changes-only plan prunes unchanged selected model",
            expected_fragments=("Plan ready (0 selected)",),
            unexpected_fragments=("Normal (1)", "orders"),
        )
    ],
    ids=["direct changes-only plan prunes unchanged selected model"],
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
        command=("--no-color", "plan", "--changes-only"),
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
            description="direct changes-only explicit select prunes unchanged selected model",
            expected_fragments=("Plan ready (0 selected)",),
            unexpected_fragments=("Models (1 standard run)", "orders"),
        )
    ],
    ids=["direct changes-only explicit select prunes unchanged selected model"],
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
        command=("--no-color", "plan", "--changes-only", "--select", "orders"),
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
            description="direct normal explicit select keeps unchanged selected model",
            expected_fragments=(
                "Plan ready (1 selected)",
                "Models (1 standard run)",
                "orders",
            ),
            unexpected_fragments=("Plan ready (0 selected)",),
        )
    ],
    ids=["direct normal explicit select keeps unchanged selected model"],
)
def test_given_built_direct_project_when_planning_selected_without_changes_only_then_keeps_model(
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
            description="direct changes-only plan keeps changed selected model",
            expected_fragments=(
                "Plan ready (1 selected)",
                "Query changed (1)",
                "orders",
                "query diff:",
            ),
            unexpected_fragments=("Plan ready (0 selected)",),
        )
    ],
    ids=["direct changes-only plan keeps changed selected model"],
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
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    (project_dir / "models" / "orders.sql").write_text(
        "MODEL (materialized table);\n\nSELECT 2 AS order_id\n",
        encoding="utf-8",
    )

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--changes-only"),
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
            description="direct changes-only plan keeps config-only changed selected model",
            expected_fragments=(
                "Plan ready (1 selected)",
                "Config changed (1)",
                "orders",
                "config diff:",
            ),
            unexpected_fragments=("Plan ready (0 selected)", "Query changed"),
        )
    ],
    ids=["direct changes-only plan keeps config-only changed selected model"],
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
        command=("--no-color", "plan", "--changes-only"),
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
            description="direct changes-only plan keeps function and downstream model",
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
    ids=["direct changes-only plan keeps function and downstream model"],
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
                "query_change_backfill full);\n\namount > 100\n"
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
        "query_change_backfill full);\n\namount >= 100\n",
        encoding="utf-8",
    )

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--changes-only", "--select", "+fact_orders"),
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
            description="direct changes-only plan keeps schema changed model",
            expected_fragments=(
                "Plan ready (1 selected)",
                "Schema changed (1)",
                "orders",
            ),
            unexpected_fragments=("Plan ready (0 selected)",),
        )
    ],
    ids=["direct changes-only plan keeps schema changed model"],
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
                "  schema_change_backfill (add_column full),\n"
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
        "  schema_change_backfill (add_column full),\n"
        "  columns (\n"
        "    order_id (type INTEGER),\n"
        "    status_rank (type INTEGER),\n"
        "  ),\n"
        ");\n\n"
        "SELECT 1 AS order_id\n",
        encoding="utf-8",
    )

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--changes-only"),
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
            description="direct changes-only plan prunes tests and audits with unchanged target",
            expected_fragments=("Plan ready (0 selected)",),
            unexpected_fragments=("Audits", "Tests", "test_orders", "not_null"),
        )
    ],
    ids=["direct changes-only plan prunes tests and audits with unchanged target"],
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
        command=("--no-color", "plan", "--changes-only"),
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
            description="direct changes-only JSON plan reports zero selected work",
            expected_selected_count=0,
            expected_model_count=0,
            expected_function_count=0,
        )
    ],
    ids=["direct changes-only JSON plan reports zero selected work"],
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
        command=("--no-color", "plan", "--changes-only", "--json"),
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
            description="direct changes-only plan observes source freshness without writing state",
            expected_fragments=("Plan ready (0 selected)",),
        )
    ],
    ids=["direct changes-only plan observes source freshness without writing state"],
)
def test_given_observable_source_freshness_when_planning_changes_only_then_does_not_write_state(
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
        command=("--no-color", "plan", "--changes-only"),
        project_dir=project_dir,
    )

    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in plan_result.stdout, plan_result.stdout
    assert not table_exists(
        db_path=project_dir / "warehouse.duckdb",
        table_name="_sqlbuild_source_freshness",
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPlanE2ETestCase(
            description="direct changes-only plan surfaces explicit source freshness errors",
            expected_fragments=(
                "column freshness requires a physical table source",
                "raw_orders",
            ),
        )
    ],
    ids=["direct changes-only plan surfaces explicit source freshness errors"],
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
        command=("--no-color", "plan", "--changes-only"),
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
            description="direct changes-only plan keeps downstream cascade",
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
    ids=["direct changes-only plan keeps downstream cascade"],
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
                "MODEL (materialized table, query_change_backfill full);\n\nSELECT 1 AS order_id\n"
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
        "MODEL (materialized table, query_change_backfill full);\n\nSELECT 2 AS order_id\n",
        encoding="utf-8",
    )

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--changes-only", "--select", "+fact_orders"),
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
        command=("--no-color", "plan", "--changes-only", "--full-refresh"),
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
        "phase": "pre_sql_ingress",
    }
    assert nodes_by_name["publish_prepared_orders"] == {
        "name": "publish_prepared_orders",
        "kind": "asset",
        "phase": "pre_sql_ingress",
    }
    assert nodes_by_name["profile_fact_orders"] == {
        "name": "profile_fact_orders",
        "kind": "task",
        "phase": "read_side",
    }
    assert nodes_by_name["notify_fact_orders"] == {
        "name": "notify_fact_orders",
        "kind": "task",
        "phase": "read_side",
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
