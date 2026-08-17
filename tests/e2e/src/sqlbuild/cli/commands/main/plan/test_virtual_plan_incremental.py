from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import (
    initialize_virtual_seeded_project,
    prepare_virtual_seeded_incremental_project,
    rewrite_incremental_orders_model,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan._test_types import (
    VirtualPlanBuildParityE2ETestCase,
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
        VirtualPlanBuildParityE2ETestCase(
            description="bounded incremental replay and cursor range match build",
            expected_plan_exit_code=0,
            expected_build_exit_code=0,
            expected_fragments=(
                "rebuild last 7d",
                "policy  replay_on_change=bounded-7d",
                "range  2026-01-02 \u2192 2026-01-04",
            ),
            unexpected_plan_fragments=("policy  replay_on_change=full",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_changed_virtual_incremental_when_planning_bounds_then_matches_build_action(
    test_case: VirtualPlanBuildParityE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_virtual_seeded_incremental_project(
        tmp_path=tmp_path,
        project_name="virtual_bounded_replay_plan_build_parity",
        incremental_strategy="delete_insert",
        replay_on_change="bounded-7d",
    )
    initialize_virtual_seeded_project(project_dir=project_dir)
    rewrite_incremental_orders_model(
        project_dir=project_dir,
        incremental_strategy="delete_insert",
        replay_on_change="bounded-7d",
        amount_expression="amount_cents + 1",
    )
    cursor_arguments: tuple[str, ...] = (
        "--start-cursor-ts",
        "2026-01-02T00:00:00",
        "--end-cursor-ts",
        "2026-01-04T00:00:00",
    )

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", *cursor_arguments),
        project_dir=project_dir,
    )

    assert plan_result.returncode == test_case.expected_plan_exit_code, (
        plan_result.stdout + plan_result.stderr
    )
    for fragment in test_case.expected_fragments:
        assert fragment in plan_result.stdout, plan_result.stdout
    for fragment in test_case.unexpected_plan_fragments:
        assert fragment not in plan_result.stdout, plan_result.stdout

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", *cursor_arguments),
        project_dir=project_dir,
    )
    assert build_result.returncode == test_case.expected_build_exit_code, (
        build_result.stdout + build_result.stderr
    )
    for fragment in test_case.expected_fragments:
        assert fragment in build_result.stdout, build_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPlanBuildParityE2ETestCase(
            description="denied snapshot full refresh is rejected by plan and build",
            expected_plan_exit_code=1,
            expected_build_exit_code=1,
            expected_fragments=(
                "error[C238]",
                "full refresh is denied for snapshot model 'customer_snapshot'",
                "snapshot_full_refresh policy",
            ),
            unexpected_plan_fragments=("Plan ready",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_denied_virtual_snapshot_full_refresh_when_planning_then_matches_build_policy(
    test_case: VirtualPlanBuildParityE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_snapshot_full_refresh_plan_build_parity",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_customers
                    schema: raw
                    table: raw_customers
                """
            ).strip()
            + "\n",
            "models/customer_snapshot.sql": dedent(
                """
                MODEL (
                  materialized snapshot,
                  unique_key [customer_id],
                  snapshot_strategy timestamp,
                  updated_at updated_at
                );

                SELECT customer_id, plan, updated_at
                FROM __source("raw_customers")
                """
            ).strip()
            + "\n",
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=dedent(
            """
            CREATE SCHEMA raw;
            CREATE TABLE raw.raw_customers AS
            SELECT 1 AS customer_id, 'basic' AS plan,
              TIMESTAMP '2024-01-01 00:00:00' AS updated_at;
            """
        ).strip(),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    initial_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert initial_build_result.returncode == 0, (
        initial_build_result.stdout + initial_build_result.stderr
    )

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--full-refresh"),
        project_dir=project_dir,
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--full-refresh"),
        project_dir=project_dir,
    )

    assert plan_result.returncode == test_case.expected_plan_exit_code
    assert build_result.returncode == test_case.expected_build_exit_code
    for result in (plan_result, build_result):
        output: str = result.stdout + result.stderr
        for fragment in test_case.expected_fragments:
            assert fragment in output, output
    for fragment in test_case.unexpected_plan_fragments:
        assert fragment not in plan_result.stdout, plan_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPlanBuildParityE2ETestCase(
            description="managed source without prior observation uses run identity in plan and build",
            expected_plan_exit_code=0,
            expected_build_exit_code=0,
            expected_fragments=(
                "Plan ready  1 selected, 1 source to load",
                "source freshness observed: 1",
                "raw_orders",
                "fact_orders",
            ),
            unexpected_plan_fragments=("source freshness incomplete: 1", "First run"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_managed_source_without_observation_when_planning_then_matches_build_identity(
    test_case: VirtualPlanBuildParityE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_managed_source_plan_build_parity",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml().replace(
                '[targets.dev]\nschema = "dev"\n\n',
                '[targets.dev]\nschema = "dev"\ndefer_sources_to = "dev"\n\n',
            ),
            "loaders/raw.py": (
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def raw_orders(ctx):\n"
                "    return [{'order_id': 7}]\n"
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
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_orders")\n'
            ),
        },
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    initial_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert initial_build_result.returncode == 0, (
        initial_build_result.stdout + initial_build_result.stderr
    )
    execute_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "DELETE FROM sqlbuild_state.source_freshness_observations "
            "WHERE virtual_environment_name = 'dev'"
        ),
    )

    command: tuple[str, ...] = ("--no-color", "plan", "--changes-only", "--load")
    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=command,
        project_dir=project_dir,
    )

    assert plan_result.returncode == test_case.expected_plan_exit_code, (
        plan_result.stdout + plan_result.stderr
    )
    for fragment in test_case.expected_fragments:
        assert fragment in plan_result.stdout, plan_result.stdout
    for fragment in test_case.unexpected_plan_fragments:
        assert fragment not in plan_result.stdout, plan_result.stdout

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--changes-only", "--load"),
        project_dir=project_dir,
    )
    assert build_result.returncode == test_case.expected_build_exit_code, (
        build_result.stdout + build_result.stderr
    )
    for fragment in test_case.expected_fragments:
        assert fragment in build_result.stdout, build_result.stdout
