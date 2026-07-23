from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.plan._test_types import (
    VirtualChangesOnlyCurrentSeedParityE2ETestCase,
    VirtualPlanBuildParityE2ETestCase,
    VirtualPlanE2ETestCase,
    VirtualSourceFreshnessPlanE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_virtual_plan_project_toml,
    build_virtual_plan_repo_files,
    seed_matching_virtual_refs,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPlanE2ETestCase(
            description="virtual plan shows query changed root and upstream changed descendants",
            seed_matching_refs=True,
            command=("--no-color", "plan", "--changes-only"),
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
    ids=lambda case: case.description,
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
            description="virtual seed change selects seed and downstream model",
            expected_unchanged_fragments=("Plan ready (0 selected)",),
            expected_fragments=(
                "Plan ready (2 selected)",
                "fact_orders",
                "order_amounts  (seed_changed)",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_seed_change_when_planning_changes_only_then_selects_dependent_model(
    test_case: VirtualSourceFreshnessPlanE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_seed_change_plan",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "seeds/schema.yml": (
                "seeds:\n"
                "  - name: order_amounts\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
                "      - name: amount_cents\n"
                "        type: INTEGER\n"
            ),
            "seeds/order_amounts.csv": "order_id,amount_cents\n1,100\n",
            "models/fact_orders.sql": (
                "MODEL (materialized table);\n\n"
                "SELECT order_id, amount_cents / 100.0 AS amount_dollars "
                'FROM __seed("order_amounts")\n'
            ),
        },
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    initial_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert initial_build_result.returncode == 0, (
        initial_build_result.stdout + initial_build_result.stderr
    )

    default_plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan"),
        project_dir=project_dir,
    )
    assert default_plan_result.returncode == 0, default_plan_result.stderr
    assert "Plan ready (2 selected)" in default_plan_result.stdout
    assert "order_amounts" in default_plan_result.stdout
    assert "fact_orders" in default_plan_result.stdout

    unchanged_plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--changes-only"),
        project_dir=project_dir,
    )
    assert unchanged_plan_result.returncode == 0, unchanged_plan_result.stderr
    for fragment in test_case.expected_unchanged_fragments:
        assert fragment in unchanged_plan_result.stdout, unchanged_plan_result.stdout
    assert "order_amounts" not in unchanged_plan_result.stdout
    assert "fact_orders" not in unchanged_plan_result.stdout

    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "order_id,amount_cents\n1,200\n",
        encoding="utf-8",
    )
    changed_plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--changes-only"),
        project_dir=project_dir,
    )

    assert changed_plan_result.returncode == 0, changed_plan_result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in changed_plan_result.stdout, changed_plan_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualChangesOnlyCurrentSeedParityE2ETestCase(
            description="virtual changes-only plan matches build when a current seed is pruned",
            expected_plan_selected_fragment="Plan ready (1 selected)",
            expected_kept_model="fact_orders",
            expected_pruned_seed="order_amounts",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_current_seed_when_planning_changes_only_then_matches_build(
    test_case: VirtualChangesOnlyCurrentSeedParityE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_changes_only_current_seed_parity",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "seeds/schema.yml": (
                "seeds:\n"
                "  - name: order_amounts\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
                "      - name: amount_cents\n"
                "        type: INTEGER\n"
            ),
            "seeds/order_amounts.csv": "order_id,amount_cents\n1,100\n",
            "models/fact_orders.sql": (
                'MODEL (materialized table, run_despite_unchanged "always");\n\n'
                'SELECT order_id, amount_cents FROM __seed("order_amounts")\n'
            ),
        },
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    initial_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert initial_build_result.returncode == 0, (
        initial_build_result.stdout + initial_build_result.stderr
    )

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--changes-only"),
        project_dir=project_dir,
    )
    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    assert test_case.expected_plan_selected_fragment in plan_result.stdout
    assert test_case.expected_kept_model in plan_result.stdout
    assert "Plan ready (0 selected)" not in plan_result.stdout

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--changes-only"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    assert test_case.expected_kept_model in build_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPlanBuildParityE2ETestCase(
            description="detached virtual environment is rejected by plan and build",
            expected_plan_exit_code=1,
            expected_build_exit_code=1,
            expected_fragments=("error[S028]", "detached"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_detached_virtual_environment_when_planning_and_building_then_both_reject(
    test_case: VirtualPlanBuildParityE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_detached_plan_build_parity",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml().replace(
                'schema = "sqlbuild_state"\n\n',
                'schema = "sqlbuild_state"\nunsuffixed_virtual_env = "dev"\n\n',
            ),
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS id\n",
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
    detach_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "detach", "--allow-copy"),
        project_dir=project_dir,
        input_text="detach dev\n",
    )
    assert detach_result.returncode == 0, detach_result.stdout + detach_result.stderr

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--changes-only"),
        project_dir=project_dir,
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--changes-only"),
        project_dir=project_dir,
    )

    assert plan_result.returncode == test_case.expected_plan_exit_code
    assert build_result.returncode == test_case.expected_build_exit_code
    for result in (plan_result, build_result):
        output: str = result.stdout + result.stderr
        for fragment in test_case.expected_fragments:
            assert fragment in output, output


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPlanBuildParityE2ETestCase(
            description="new virtual environment inherits current baseline read only",
            expected_plan_exit_code=0,
            expected_build_exit_code=0,
            expected_fragments=("Plan ready (0 selected)",),
            unexpected_plan_fragments=("First run",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_new_virtual_environment_when_planning_then_inherits_baseline_without_writing(
    test_case: VirtualPlanBuildParityE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_new_environment_plan_build_parity",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS id\n",
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
    state_db_path: Path = project_dir / "state.duckdb"
    pr_ref_count_sql: str = (
        "SELECT COUNT(*) FROM sqlbuild_state.virtual_environment_node_refs "
        "WHERE virtual_environment_name = 'pr'"
    )
    assert query_duckdb(db_path=state_db_path, sql=pr_ref_count_sql) == [(0,)]

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--virtual-env", "pr", "--changes-only"),
        project_dir=project_dir,
    )

    assert plan_result.returncode == test_case.expected_plan_exit_code, (
        plan_result.stdout + plan_result.stderr
    )
    for fragment in test_case.expected_fragments:
        assert fragment in plan_result.stdout, plan_result.stdout
    for fragment in test_case.unexpected_plan_fragments:
        assert fragment not in plan_result.stdout, plan_result.stdout
    assert query_duckdb(db_path=state_db_path, sql=pr_ref_count_sql) == [(0,)]

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr", "--changes-only"),
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
            description="explicit model selection includes stale upstream seed",
            expected_plan_exit_code=0,
            expected_build_exit_code=0,
            expected_fragments=("Plan ready (2 selected)", "order_amounts", "fact_orders"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_stale_seed_upstream_when_planning_selected_model_then_matches_build_closure(
    test_case: VirtualPlanBuildParityE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_selected_model_stale_seed_plan_build_parity",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "seeds/schema.yml": (
                "seeds:\n"
                "  - name: order_amounts\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
                "      - name: amount_cents\n"
                "        type: INTEGER\n"
            ),
            "seeds/order_amounts.csv": "order_id,amount_cents\n1,100\n",
            "models/fact_orders.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT order_id, amount_cents FROM __seed("order_amounts")\n'
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
    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "order_id,amount_cents\n1,200\n",
        encoding="utf-8",
    )

    command: tuple[str, ...] = ("--no-color", "plan", "--select", "fact_orders")
    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=command,
        project_dir=project_dir,
    )

    assert plan_result.returncode == test_case.expected_plan_exit_code, (
        plan_result.stdout + plan_result.stderr
    )
    for fragment in test_case.expected_fragments:
        assert fragment in plan_result.stdout, plan_result.stdout

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "fact_orders"),
        project_dir=project_dir,
    )
    assert build_result.returncode == test_case.expected_build_exit_code, (
        build_result.stdout + build_result.stderr
    )
    for fragment in test_case.expected_fragments:
        assert fragment in build_result.stdout, build_result.stdout
