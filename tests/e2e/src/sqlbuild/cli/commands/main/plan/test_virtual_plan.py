from __future__ import annotations

import json
import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.plan._test_types import (
    VirtualPlanE2ETestCase,
    VirtualPlanJsonE2ETestCase,
    VirtualPlanSelectionGuardE2ETestCase,
    VirtualSourceFreshnessPlanE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_virtual_plan_project_toml,
    build_virtual_plan_repo_files,
    seed_matching_virtual_refs,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPlanE2ETestCase(
            description="virtual plan shows query changed root and upstream changed descendants",
            seed_matching_refs=True,
            command=("--no-color", "plan"),
            expected_fragments=(
                "Plan ready (2 selected)",
                "Virtual environment",
                "name: dev",
                "status: working",
                "stale models: 2",
                "stale model set: fact_orders, stg_orders",
                "stale roots: 1",
                "stale root set: stg_orders",
                "Query changed (1)",
                "stg_orders",
                "Upstream changed (1)",
                "fact_orders",
                "cause: stg_orders (query changed)",
            ),
            unexpected_fragments=("dim_customers", "First run"),
        )
    ],
    ids=["virtual plan shows query changed root and upstream changed descendants"],
)
def test_given_virtual_plan_with_seeded_baseline_when_running_cli_then_it_uses_virtual_reasons(
    test_case: VirtualPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    baseline_project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_project_baseline",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_project",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 2 AS id"),
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr

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
        VirtualSourceFreshnessPlanE2ETestCase(
            description="virtual plan observes current source freshness before build persistence",
            expected_unchanged_fragments=("Plan ready (0 selected)",),
            expected_fragments=(
                "Plan ready (1 selected)",
                "source freshness observed: 1",
                "source freshness observed set: raw_orders",
                "stale model set: fact_orders",
                "fact_orders",
            ),
        )
    ],
    ids=["virtual plan observes current source freshness before build persistence"],
)
def test_given_virtual_source_freshness_change_when_planning_then_selects_downstream_model(
    test_case: VirtualSourceFreshnessPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_source_freshness_plan",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_orders
                    schema: raw
                    table: raw_orders
                    freshness:
                      strategy: column
                      column: data_version
                      type: integer
                """
            ).strip()
            + "\n",
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=dedent(
            """
            CREATE SCHEMA raw;
            CREATE TABLE raw.raw_orders (id INTEGER, data_version INTEGER);
            INSERT INTO raw.raw_orders VALUES (7, 1);
            """
        ).strip(),
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

    unchanged_plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan"),
        project_dir=project_dir,
    )
    assert unchanged_plan_result.returncode == 0, unchanged_plan_result.stderr
    fragment: str
    for fragment in test_case.expected_unchanged_fragments:
        assert fragment in unchanged_plan_result.stdout, unchanged_plan_result.stdout

    unchanged_changes_only_plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--changes-only"),
        project_dir=project_dir,
    )
    assert unchanged_changes_only_plan_result.returncode == 0, (
        unchanged_changes_only_plan_result.stderr
    )
    for fragment in test_case.expected_unchanged_fragments:
        assert fragment in unchanged_changes_only_plan_result.stdout, (
            unchanged_changes_only_plan_result.stdout
        )

    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="UPDATE raw.raw_orders SET id = 8, data_version = 2",
    )

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--changes-only"),
        project_dir=project_dir,
    )

    assert plan_result.returncode == 0, plan_result.stderr
    output: str = plan_result.stdout
    for fragment in test_case.expected_fragments:
        assert fragment in output, output
    for fragment in test_case.unexpected_fragments:
        assert fragment not in output, output


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessPlanE2ETestCase(
            description="virtual plan respects timestamp source freshness lag tolerance",
            expected_unchanged_fragments=(
                "Plan ready (0 selected)",
                "source freshness unchanged: 1",
                "source freshness unchanged set: raw_orders",
            ),
            expected_fragments=("Plan ready (1 selected)", "fact_orders"),
        )
    ],
    ids=["virtual plan respects timestamp source freshness lag tolerance"],
)
def test_given_virtual_timestamp_lag_tolerance_when_planning_then_skips_within_tolerance(
    test_case: VirtualSourceFreshnessPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_source_freshness_plan_lag_tolerance",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_orders
                    schema: raw
                    table: raw_orders
                    freshness:
                      strategy: column
                      column: data_version
                      type: timestamp
                      lag_tolerance: 10m
                """
            ).strip()
            + "\n",
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=dedent(
            """
            CREATE SCHEMA raw;
            CREATE TABLE raw.raw_orders (id INTEGER, data_version TIMESTAMP);
            INSERT INTO raw.raw_orders VALUES (7, '2026-01-01 12:00:00');
            """
        ).strip(),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stderr
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert build_result.returncode == 0, build_result.stderr

    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="UPDATE raw.raw_orders SET id = 8, data_version = '2026-01-01 12:05:00'",
    )
    within_tolerance_plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--changes-only"), project_dir=project_dir
    )

    assert within_tolerance_plan_result.returncode == 0, within_tolerance_plan_result.stderr
    fragment: str
    for fragment in test_case.expected_unchanged_fragments:
        assert fragment in within_tolerance_plan_result.stdout, within_tolerance_plan_result.stdout

    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="UPDATE raw.raw_orders SET id = 9, data_version = '2026-01-01 12:11:00'",
    )
    beyond_tolerance_plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--changes-only"), project_dir=project_dir
    )

    assert beyond_tolerance_plan_result.returncode == 0, beyond_tolerance_plan_result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in beyond_tolerance_plan_result.stdout, beyond_tolerance_plan_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessPlanE2ETestCase(
            description="virtual plan keeps unknown source freshness stale",
            expected_unchanged_fragments=(
                "Plan ready (1 selected)",
                "source freshness incomplete: 1",
                "source freshness incomplete set: raw_orders",
                "source freshness incomplete models: fact_orders",
                "stale model set: fact_orders",
            ),
            expected_fragments=("Plan ready (1 selected)", "fact_orders"),
        )
    ],
    ids=["virtual plan keeps unknown source freshness stale"],
)
def test_given_virtual_source_without_freshness_when_planning_then_downstream_stays_stale(
    test_case: VirtualSourceFreshnessPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_unknown_source_freshness_plan",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_orders
                    schema: raw
                    table: raw_orders
                """
            ).strip()
            + "\n",
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=dedent(
            """
            CREATE SCHEMA raw;
            CREATE TABLE raw.raw_orders (id INTEGER);
            INSERT INTO raw.raw_orders VALUES (7);
            """
        ).strip(),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stderr
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert build_result.returncode == 0, build_result.stderr

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--changes-only"), project_dir=project_dir
    )

    assert plan_result.returncode == 0, plan_result.stderr
    fragment: str
    for fragment in test_case.expected_unchanged_fragments:
        assert fragment in plan_result.stdout, plan_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessPlanE2ETestCase(
            description="virtual plan propagates source freshness through views",
            expected_unchanged_fragments=("Plan ready (0 selected)",),
            expected_fragments=(
                "Plan ready (2 selected)",
                "source freshness observed: 1",
                "source freshness observed set: raw_orders",
                "stale model set: fact_orders, stg_orders",
                "stg_orders",
                "fact_orders",
            ),
        )
    ],
    ids=["virtual plan propagates source freshness through views"],
)
def test_given_virtual_source_freshness_through_view_when_planning_then_selects_downstream_path(
    test_case: VirtualSourceFreshnessPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_source_freshness_view_plan",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_orders
                    schema: raw
                    table: raw_orders
                    freshness:
                      strategy: column
                      column: data_version
                      type: integer
                """
            ).strip()
            + "\n",
            "models/stg_orders.sql": (
                'MODEL (materialized view);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __ref("stg_orders")\n'
            ),
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=dedent(
            """
            CREATE SCHEMA raw;
            CREATE TABLE raw.raw_orders (id INTEGER, data_version INTEGER);
            INSERT INTO raw.raw_orders VALUES (7, 1);
            """
        ).strip(),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stderr
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert build_result.returncode == 0, build_result.stderr
    unchanged_plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--changes-only"), project_dir=project_dir
    )
    assert unchanged_plan_result.returncode == 0, unchanged_plan_result.stderr
    fragment: str
    for fragment in test_case.expected_unchanged_fragments:
        assert fragment in unchanged_plan_result.stdout, unchanged_plan_result.stdout

    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="UPDATE raw.raw_orders SET id = 8, data_version = 2",
    )
    changed_plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--changes-only"), project_dir=project_dir
    )

    assert changed_plan_result.returncode == 0, changed_plan_result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in changed_plan_result.stdout, changed_plan_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPlanJsonE2ETestCase(
            description="virtual plan json explains source freshness currentness",
            expected_json_fragments=(
                '"virtual_environment_name": "dev"',
                '"virtual_environment_status": "working"',
                '"virtual_source_freshness_observed_source_names": [',
                '"raw_orders"',
                '"virtual_source_freshness_incomplete_source_names": []',
                '"virtual_source_freshness_incomplete_model_names": []',
                '"virtual_stale_model_names": [',
                '"virtual_stale_root_names": []',
            ),
        )
    ],
    ids=["virtual plan json explains source freshness currentness"],
)
def test_given_virtual_source_freshness_when_planning_json_then_metadata_reports_currentness(
    test_case: VirtualPlanJsonE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_source_freshness_plan_json",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_orders
                    schema: raw
                    table: raw_orders
                    freshness:
                      strategy: column
                      column: data_version
                      type: integer
                """
            ).strip()
            + "\n",
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=dedent(
            """
            CREATE SCHEMA raw;
            CREATE TABLE raw.raw_orders (id INTEGER, data_version INTEGER);
            INSERT INTO raw.raw_orders VALUES (7, 1);
            """
        ).strip(),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stderr
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert build_result.returncode == 0, build_result.stderr
    unchanged_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("plan", "--changes-only", "--json"), project_dir=project_dir
    )
    assert unchanged_result.returncode == 0, unchanged_result.stderr
    unchanged_payload: dict[str, object] = json.loads(unchanged_result.stdout)
    assert unchanged_payload["metadata"] == {
        "virtual_environment_name": "dev",
        "virtual_environment_status": "finalized",
        "virtual_mode": True,
        "virtual_source_freshness_observed_source_names": ["raw_orders"],
        "virtual_source_freshness_unchanged_source_names": ["raw_orders"],
        "virtual_source_freshness_incomplete_source_names": [],
        "virtual_source_freshness_incomplete_model_names": [],
        "virtual_stale_model_names": [],
        "virtual_stale_root_names": [],
        "virtual_remaining_stale_model_names": [],
    }

    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="UPDATE raw.raw_orders SET id = 8, data_version = 2",
    )
    changed_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("plan", "--changes-only", "--json"), project_dir=project_dir
    )

    assert changed_result.returncode == 0, changed_result.stderr
    output: str = changed_result.stdout
    parsed: dict[str, object] = json.loads(output)
    assert "metadata" in parsed
    fragment: str
    for fragment in test_case.expected_json_fragments:
        assert fragment in output, output


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPlanE2ETestCase(
            description="virtual plan shows config changed root without query diff",
            seed_matching_refs=True,
            command=("--no-color", "plan"),
            expected_fragments=(
                "Plan ready (2 selected)",
                "stale root set: stg_orders",
                "Config changed (1)",
                "stg_orders",
                "config diff:",
                '"materialized": "view"',
                '"materialized": "table"',
                "Upstream changed (1)",
                "fact_orders",
                "cause: stg_orders (config changed)",
            ),
            unexpected_fragments=("Query changed", "query diff:"),
        )
    ],
    ids=["virtual plan shows config changed root without query diff"],
)
def test_given_virtual_plan_with_config_change_when_running_cli_then_it_uses_config_reason(
    test_case: VirtualPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    baseline_project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_config_baseline",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id")[
                "sqlbuild_project.toml"
            ],
            "models/stg_orders.sql": "MODEL (materialized view);\n\nSELECT 1 AS id\n",
            "models/fact_orders.sql": 'MODEL ();\n\nSELECT id FROM __ref("stg_orders")\n',
        },
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_config_current",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id")[
                "sqlbuild_project.toml"
            ],
            "models/stg_orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS id\n",
            "models/fact_orders.sql": 'MODEL ();\n\nSELECT id FROM __ref("stg_orders")\n',
        },
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
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
            description="virtual plan shows function-driven query changed root",
            seed_matching_refs=True,
            command=("--no-color", "plan"),
            expected_fragments=(
                "Plan ready (3 selected)",
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
    ids=["virtual plan shows function-driven query changed root"],
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
        "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, query_change_backfill full);\n\n"
        "amount > 9\n"
    )
    current_function_sql: str = (
        "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, query_change_backfill full);\n\n"
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
            command=("--no-color", "plan"),
            expected_fragments=(
                "Changed functions (1)",
                "is_large_order",
                "policy: query_change_backfill=full",
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
    ids=["virtual plan after build shows changed function diff"],
)
def test_given_virtual_build_then_function_change_when_running_plan_then_it_shows_function_diff(
    test_case: VirtualPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    initial_function_sql: str = (
        "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, query_change_backfill full);\n\n"
        "amount > 9\n"
    )
    changed_function_sql: str = (
        "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, query_change_backfill full);\n\n"
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


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPlanE2ETestCase(
            description="virtual plan selects nothing when all bound refs match expected hashes",
            seed_matching_refs=True,
            command=("--no-color", "plan"),
            expected_fragments=(
                "Plan ready (0 selected)",
                "Virtual environment",
                "name: dev",
                "status: finalized",
                "stale models: 0",
            ),
            unexpected_fragments=("First run", "fact_orders", "dim_customers", "stg_orders"),
        )
    ],
    ids=["virtual plan selects nothing when all bound refs match expected hashes"],
)
def test_given_virtual_plan_with_matching_refs_when_running_cli_then_it_selects_nothing(
    test_case: VirtualPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_project",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    seed_matching_virtual_refs(project_dir=project_dir)

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
            description="virtual plan with multiple stale roots excludes unaffected branches",
            seed_matching_refs=True,
            command=("--no-color", "plan"),
            expected_fragments=(
                "Plan ready (3 selected)",
                "stale roots: 2",
                "stale root set: dim_customers, stg_orders",
                "stale models: 3",
                "stale model set: dim_customers, fact_orders, stg_orders",
                "Query changed (2)",
                "stg_orders",
                "dim_customers",
                "Upstream changed (1)",
                "fact_orders",
            ),
            unexpected_fragments=("static_model",),
        )
    ],
    ids=["virtual plan with multiple stale roots excludes unaffected branches"],
)
def test_given_virtual_plan_with_multiple_stale_roots_when_running_cli_then_it_excludes_unaffected(
    test_case: VirtualPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    baseline_project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_multi_root_baseline",
        repo_files=build_virtual_plan_repo_files(
            stg_orders_sql="SELECT 1 AS id",
            dim_customers_sql="SELECT 1 AS customer_id",
        )
        | {"models/static_model.sql": "MODEL ();\n\nSELECT 99 AS static_value\n"},
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_multi_root",
        repo_files=build_virtual_plan_repo_files(
            stg_orders_sql="SELECT 2 AS id",
            dim_customers_sql="SELECT 2 AS customer_id",
        )
        | {"models/static_model.sql": "MODEL ();\n\nSELECT 99 AS static_value\n"},
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
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
            description="virtual plan explicit select bypasses stale-driven selection",
            seed_matching_refs=True,
            command=("--no-color", "plan", "--select", "dim_customers"),
            expected_fragments=(
                "Plan ready (1 selected)",
                "Virtual environment",
                "stale roots: 1",
                "stale root set: stg_orders",
                "dim_customers",
            ),
            unexpected_fragments=("Upstream changed (1)",),
        )
    ],
    ids=["virtual plan explicit select bypasses stale-driven selection"],
)
def test_given_virtual_plan_with_explicit_select_when_running_cli_then_it_bypasses_default_scope(
    test_case: VirtualPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    baseline_project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_select_baseline",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_select_current",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 2 AS id"),
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
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
        VirtualPlanSelectionGuardE2ETestCase(
            description="selected downstream with stale upstream blocks",
            command=("--no-color", "plan", "--select", "fact_orders"),
            expected_exit_code=1,
            expected_fragments=(
                "missing stale required upstream models: stg_orders",
                "--include-stale-upstreams",
            ),
        )
    ],
    ids=["selected downstream with stale upstream blocks"],
)
def test_given_virtual_plan_selected_downstream_with_stale_upstream_when_running_then_it_blocks(
    test_case: VirtualPlanSelectionGuardE2ETestCase,
    tmp_path: Path,
) -> None:
    baseline_project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_guard_baseline",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_guard_current",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 2 AS id"),
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    seed_matching_virtual_refs(
        project_dir=project_dir,
        source_project_dir=baseline_project_dir,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code
    output: str = result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in output


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPlanSelectionGuardE2ETestCase(
            description="include stale upstreams and changes only narrows scope",
            command=(
                "--no-color",
                "plan",
                "--select",
                "fact_orders",
                "--select",
                "dim_customers",
                "--include-stale-upstreams",
                "--changes-only",
            ),
            expected_exit_code=0,
            expected_fragments=("Plan ready (2 selected)", "stg_orders", "fact_orders"),
            unexpected_fragments=("dim_customers",),
        )
    ],
    ids=["include stale upstreams and changes only narrows scope"],
)
def test_given_virtual_plan_include_stale_upstreams_when_running_then_it_expands_minimally(
    test_case: VirtualPlanSelectionGuardE2ETestCase,
    tmp_path: Path,
) -> None:
    baseline_project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_include_baseline",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_include_current",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 2 AS id"),
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    seed_matching_virtual_refs(
        project_dir=project_dir,
        source_project_dir=baseline_project_dir,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stderr
    output: str = result.stdout
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in output
    for fragment in test_case.unexpected_fragments:
        assert fragment not in output


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPlanJsonE2ETestCase(
            description="virtual plan json includes metadata fields",
            expected_json_fragments=(
                '"metadata"',
                '"virtual_environment_name": "dev"',
                '"virtual_environment_status": "working"',
                '"virtual_stale_model_names"',
                '"virtual_stale_root_names"',
            ),
        )
    ],
    ids=["virtual plan json includes metadata fields"],
)
def test_given_virtual_plan_json_when_running_cli_then_it_includes_virtual_metadata(
    test_case: VirtualPlanJsonE2ETestCase,
    tmp_path: Path,
) -> None:
    baseline_project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_json_baseline",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_plan_json_current",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 2 AS id"),
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    seed_matching_virtual_refs(
        project_dir=project_dir,
        source_project_dir=baseline_project_dir,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("plan", "--json"),
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr
    output: str = result.stdout
    parsed: dict[str, object] = json.loads(output)
    assert "metadata" in parsed
    fragment: str
    for fragment in test_case.expected_json_fragments:
        assert fragment in output, output
