from __future__ import annotations

import json
import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.plan._test_types import (
    VirtualPlanJsonE2ETestCase,
    VirtualSourceFreshnessPlanE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_virtual_plan_project_toml,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessPlanE2ETestCase(
            description="virtual plan observes current source freshness before build persistence",
            expected_unchanged_fragments=(
                "Plan ready (0 selected)",
                "source freshness observed: 1",
                "source freshness observed set: raw_orders",
            ),
            expected_fragments=(
                "Plan ready (1 selected)",
                "source freshness observed: 1",
                "source freshness observed set: raw_orders",
                "stale model set: fact_orders",
                "fact_orders",
            ),
        )
    ],
    ids=lambda case: case.description,
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
    assert "Plan ready (1 selected)" in unchanged_plan_result.stdout
    assert "fact_orders" in unchanged_plan_result.stdout
    for fragment in test_case.expected_unchanged_fragments[1:]:
        assert fragment in unchanged_plan_result.stdout, unchanged_plan_result.stdout

    unchanged_changes_only_plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--changes-only"),
        project_dir=project_dir,
    )
    assert unchanged_changes_only_plan_result.returncode == 0, (
        unchanged_changes_only_plan_result.stderr
    )
    fragment: str
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
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
    ids=lambda case: case.description,
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
        command=("plan", "--json", "--changes-only"), project_dir=project_dir
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
        command=("plan", "--json"), project_dir=project_dir
    )

    assert changed_result.returncode == 0, changed_result.stderr
    output: str = changed_result.stdout
    parsed: dict[str, object] = json.loads(output)
    assert "metadata" in parsed
    fragment: str
    for fragment in test_case.expected_json_fragments:
        assert fragment in output, output
