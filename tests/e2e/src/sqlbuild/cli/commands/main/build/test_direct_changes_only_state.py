"""E2E tests for standard changes-only state and downstream data correctness."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    DirectChangesOnlySeedBuildE2ETestCase,
    DirectChangesOnlyStateBuildE2ETestCase,
    DirectReuseFromBuildE2ETestCase,
    DirectSeedChangesOnlyGapE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import (
    prepare_direct_changes_only_two_model_project,
    prepare_direct_custom_reuse_from_project,
    prepare_direct_reuse_from_audit_project,
    prepare_direct_reuse_from_multi_schema_project,
    prepare_direct_reuse_from_project,
    prepare_direct_snapshot_reuse_from_project,
    write_direct_changes_only_stg_orders,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    query_duckdb,
    run_sqb,
    table_exists,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlyStateBuildE2ETestCase(
            description="changes-only rebuilds downstream data",
            project_name="direct_changes_only_build_updates_downstream",
            initial_amount_cents=100,
            changed_amount_cents=125,
            expected_initial_amount_dollars=1.0,
            expected_changed_amount_dollars=1.25,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_upstream_query_change_when_building_changes_only_then_rebuilds_downstream_data(
    test_case: DirectChangesOnlyStateBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_direct_changes_only_two_model_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        amount_cents=test_case.initial_amount_cents,
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    initial_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr

    write_direct_changes_only_stg_orders(
        project_dir=project_dir, amount_cents=test_case.changed_amount_cents
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )

    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    assert "Plan ready (2 selected)" in build_result.stdout
    assert "stg_orders" in build_result.stdout
    assert "fact_orders" in build_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT amount_cents, amount_dollars FROM fact_orders ORDER BY order_id",
    ) == [(test_case.changed_amount_cents, test_case.expected_changed_amount_dollars)]


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlySeedBuildE2ETestCase(
            description="seed change reloads seed and downstream model",
            project_name="direct_changes_only_seed_identity",
            initial_seed_contents="order_id,amount_cents\n1,100\n",
            changed_seed_contents="order_id,amount_cents\n1,125\n",
            expected_plan_selected_count=2,
            expected_amount_dollars=1.25,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seed_change_when_building_changes_only_then_reloads_seed_and_downstream_model(
    test_case: DirectChangesOnlySeedBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": (
                f'name = "{test_case.project_name}"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "seeds/schema.yml": (
                "seeds:\n"
                "  - name: order_amounts\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
                "      - name: amount_cents\n"
                "        type: INTEGER\n"
            ),
            "seeds/order_amounts.csv": test_case.initial_seed_contents,
            "models/fact_orders.sql": (
                "MODEL (materialized table);\n\n"
                "SELECT order_id, amount_cents / 100.0 AS amount_dollars "
                'FROM __seed("order_amounts")\n'
            ),
        },
    )
    db_path: Path = project_dir / "warehouse.duckdb"

    initial_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr

    unchanged_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert unchanged_result.returncode == 0, unchanged_result.stdout + unchanged_result.stderr
    assert "Plan ready (0 selected)" in unchanged_result.stdout
    assert "order_amounts" not in unchanged_result.stdout
    assert "fact_orders" not in unchanged_result.stdout

    (project_dir / "seeds" / "order_amounts.csv").write_text(
        test_case.changed_seed_contents, encoding="utf-8"
    )
    changed_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert changed_result.returncode == 0, changed_result.stdout + changed_result.stderr
    assert (
        f"Plan ready ({test_case.expected_plan_selected_count} selected)" in changed_result.stdout
    )
    assert "order_amounts  (seed_changed)" in changed_result.stdout
    assert "seed      order_amounts" in changed_result.stdout
    assert "fact_orders" in changed_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT amount_dollars FROM fact_orders ORDER BY order_id",
    ) == [(test_case.expected_amount_dollars,)]


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlySeedBuildE2ETestCase(
            description=(
                "selected leaf warns on changed out-of-selection seed until closure rebuild"
            ),
            project_name="direct_changes_only_seed_selection_staleness",
            initial_seed_contents="order_id,amount_cents\n1,100\n",
            changed_seed_contents="order_id,amount_cents\n1,125\n",
            expected_plan_selected_count=2,
            expected_amount_dollars=1.25,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seed_change_out_of_selection_when_building_leaf_then_warns_until_closure(
    test_case: DirectChangesOnlySeedBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": (
                f'name = "{test_case.project_name}"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "seeds/schema.yml": (
                "seeds:\n"
                "  - name: order_amounts\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
                "      - name: amount_cents\n"
                "        type: INTEGER\n"
            ),
            "seeds/order_amounts.csv": test_case.initial_seed_contents,
            "models/fact_orders.sql": (
                "MODEL (materialized table);\n\n"
                "SELECT order_id, amount_cents / 100.0 AS amount_dollars "
                'FROM __seed("order_amounts")\n'
            ),
        },
    )
    db_path: Path = project_dir / "warehouse.duckdb"

    initial_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr

    (project_dir / "seeds" / "order_amounts.csv").write_text(
        test_case.changed_seed_contents, encoding="utf-8"
    )
    narrow_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "fact_orders"),
        project_dir=project_dir,
    )
    narrow_output: str = narrow_result.stdout + narrow_result.stderr
    assert narrow_result.returncode == 0, narrow_output
    assert "selected model 'fact_orders' will build on" in narrow_output
    assert "- order_amounts" in narrow_output
    assert "seed      order_amounts" not in narrow_output
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT amount_dollars FROM fact_orders ORDER BY order_id",
    ) == [(1.0,)]

    closure_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "+fact_orders"),
        project_dir=project_dir,
    )
    closure_output: str = closure_result.stdout + closure_result.stderr
    assert closure_result.returncode == 0, closure_output
    assert f"Plan ready ({test_case.expected_plan_selected_count} selected)" in closure_output
    assert "seed      order_amounts" in closure_output
    assert "selected model 'fact_orders' will build on" not in closure_output
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT amount_dollars FROM fact_orders ORDER BY order_id",
    ) == [(test_case.expected_amount_dollars,)]


@pytest.mark.parametrize(
    "test_case",
    [
        DirectSeedChangesOnlyGapE2ETestCase(
            description="standalone seed writes fingerprint for changes-only build",
            project_name="direct_standalone_seed_fingerprint",
            expected_plan_fragment="Plan ready (1 selected)",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_standalone_seed_when_building_changes_only_then_seed_is_current(
    test_case: DirectSeedChangesOnlyGapE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": (
                f'name = "{test_case.project_name}"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
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

    seed_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "seed"), project_dir=project_dir
    )
    assert seed_result.returncode == 0, seed_result.stdout + seed_result.stderr

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    assert test_case.expected_plan_fragment in build_result.stdout
    assert "seed      order_amounts" not in build_result.stdout
    assert "fact_orders" in build_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DirectSeedChangesOnlyGapE2ETestCase(
            description="seed change plan json reports changed reason",
            project_name="direct_seed_plan_json_reason",
            expected_seed_payload=(
                {
                    "name": "order_amounts",
                    "reason": "config_changed",
                    "qualified_name": "main.order_amounts",
                },
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seed_change_when_planning_json_then_seed_reason_is_reported(
    test_case: DirectSeedChangesOnlyGapE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": (
                f'name = "{test_case.project_name}"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
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
    initial_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr
    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "order_id,amount_cents\n1,125\n", encoding="utf-8"
    )

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--json"), project_dir=project_dir
    )

    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    payload: dict[str, object] = json.loads(plan_result.stdout)
    seeds: object = payload["seeds"]
    assert seeds == list(test_case.expected_seed_payload)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectSeedChangesOnlyGapE2ETestCase(
            description="single changed seed only rebuilds dependent branch",
            project_name="direct_multi_seed_closure",
            expected_plan_fragment="Plan ready (2 selected)",
            expected_fact_order_rows=((125,),),
            expected_customer_rows=(("Ada",),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_multiple_seed_branches_when_one_seed_changes_then_only_dependent_branch_runs(
    test_case: DirectSeedChangesOnlyGapE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": (
                f'name = "{test_case.project_name}"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "seeds/schema.yml": (
                "seeds:\n"
                "  - name: order_amounts\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
                "      - name: amount_cents\n"
                "        type: INTEGER\n"
                "  - name: customer_names\n"
                "    columns:\n"
                "      - name: customer_id\n"
                "        type: INTEGER\n"
                "      - name: customer_name\n"
                "        type: VARCHAR\n"
            ),
            "seeds/order_amounts.csv": "order_id,amount_cents\n1,100\n",
            "seeds/customer_names.csv": "customer_id,customer_name\n1,Ada\n",
            "models/fact_orders.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT order_id, amount_cents FROM __seed("order_amounts")\n'
            ),
            "models/dim_customers.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT customer_id, customer_name FROM __seed("customer_names")\n'
            ),
        },
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    initial_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr
    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "order_id,amount_cents\n1,125\n", encoding="utf-8"
    )

    changed_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert changed_result.returncode == 0, changed_result.stdout + changed_result.stderr
    assert test_case.expected_plan_fragment in changed_result.stdout
    assert "seed      order_amounts" in changed_result.stdout
    assert "fact_orders" in changed_result.stdout
    assert "seed      customer_names" not in changed_result.stdout
    assert "dim_customers" not in changed_result.stdout
    assert query_duckdb(
        db_path=db_path, sql="SELECT amount_cents FROM fact_orders ORDER BY order_id"
    ) == list(test_case.expected_fact_order_rows)
    assert query_duckdb(
        db_path=db_path, sql="SELECT customer_name FROM dim_customers ORDER BY customer_id"
    ) == list(test_case.expected_customer_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectSeedChangesOnlyGapE2ETestCase(
            description="seed column type change selects seed and downstream model",
            project_name="direct_seed_schema_identity",
            expected_plan_fragment="Plan ready (2 selected)",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seed_schema_change_when_building_changes_only_then_seed_and_downstream_run(
    test_case: DirectSeedChangesOnlyGapE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": (
                f'name = "{test_case.project_name}"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
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
    initial_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr
    (project_dir / "seeds" / "schema.yml").write_text(
        "seeds:\n"
        "  - name: order_amounts\n"
        "    columns:\n"
        "      - name: order_id\n"
        "        type: BIGINT\n"
        "      - name: amount_cents\n"
        "        type: INTEGER\n",
        encoding="utf-8",
    )

    changed_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert changed_result.returncode == 0, changed_result.stdout + changed_result.stderr
    assert test_case.expected_plan_fragment in changed_result.stdout
    assert "order_amounts  (seed_changed)" in changed_result.stdout
    assert "seed      order_amounts" in changed_result.stdout
    assert "fact_orders" in changed_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DirectSeedChangesOnlyGapE2ETestCase(
            description="reuse_from builds active target when seed identity differs",
            project_name="direct_reuse_from_seed_identity",
            expected_fact_order_rows=((125,),),
            expected_customer_rows=((100,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_reuse_from_and_seed_change_when_building_dev_then_builds_active_seed_version(
    test_case: DirectSeedChangesOnlyGapE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": (
                f'name = "{test_case.project_name}"\n'
                'adapter = "duckdb"\n'
                'default_target = "prod"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.prod]\n"
                'schema = "prod"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n'
                'reuse_from = "prod"\n'
                "reuse_hard_copy = true\n"
            ),
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
    db_path: Path = project_dir / "warehouse.duckdb"
    (project_dir / "sqlbuild_local.toml").write_text('target = "prod"\n', encoding="utf-8")
    prod_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert prod_result.returncode == 0, prod_result.stdout + prod_result.stderr
    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "order_id,amount_cents\n1,125\n", encoding="utf-8"
    )
    (project_dir / "sqlbuild_local.toml").write_text('target = "dev"\n', encoding="utf-8")

    dev_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert dev_result.returncode == 0, dev_result.stdout + dev_result.stderr
    assert "seed      order_amounts" in dev_result.stdout
    assert "reuse origin target" not in dev_result.stdout
    assert query_duckdb(
        db_path=db_path, sql="SELECT amount_cents FROM prod.fact_orders ORDER BY order_id"
    ) == list(test_case.expected_customer_rows)
    assert query_duckdb(
        db_path=db_path, sql="SELECT amount_cents FROM dev.fact_orders ORDER BY order_id"
    ) == list(test_case.expected_fact_order_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlyStateBuildE2ETestCase(
            description="later unscoped build rebuilds downstream left stale by scoped build",
            project_name="direct_changes_only_build_scoped_then_later",
            initial_amount_cents=100,
            changed_amount_cents=125,
            expected_initial_amount_dollars=1.0,
            expected_changed_amount_dollars=1.25,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_scoped_upstream_changes_only_build_when_building_later_then_rebuilds_downstream(
    test_case: DirectChangesOnlyStateBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_direct_changes_only_two_model_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        amount_cents=test_case.initial_amount_cents,
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    initial_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr

    write_direct_changes_only_stg_orders(
        project_dir=project_dir, amount_cents=test_case.changed_amount_cents
    )
    scoped_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "stg_orders"),
        project_dir=project_dir,
    )

    assert scoped_result.returncode == 0, scoped_result.stdout + scoped_result.stderr
    assert "Plan ready (1 selected)" in scoped_result.stdout
    assert "stg_orders" in scoped_result.stdout
    assert "Remaining stale" in scoped_result.stdout
    assert "model set: fact_orders" in scoped_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT amount_cents, amount_dollars FROM fact_orders ORDER BY order_id",
    ) == [(test_case.initial_amount_cents, test_case.expected_initial_amount_dollars)]

    later_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )

    assert later_result.returncode == 0, later_result.stdout + later_result.stderr
    assert "Plan ready (1 selected)" in later_result.stdout
    assert "fact_orders" in later_result.stdout
    assert "Remaining stale" not in later_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT amount_cents, amount_dollars FROM fact_orders ORDER BY order_id",
    ) == [(test_case.changed_amount_cents, test_case.expected_changed_amount_dollars)]


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlyStateBuildE2ETestCase(
            description="changes-only build runs table configured duration despite unchanged",
            project_name="direct_build_run_despite_unchanged_duration",
            initial_amount_cents=100,
            changed_amount_cents=100,
            expected_initial_amount_dollars=1.0,
            expected_changed_amount_dollars=1.0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_run_despite_unchanged_duration_when_building_changes_only_then_rebuilds_downstream(
    test_case: DirectChangesOnlyStateBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": (
                f'name = "{test_case.project_name}"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    expression: SELECT 1 AS order_id, 100 AS amount_cents\n"
                "    freshness:\n"
                "      strategy: sql\n"
                "      type: timestamp\n"
                "      query: SELECT CURRENT_TIMESTAMP AS data_version\n"
                "      lag_tolerance: 30d\n"
            ),
            "models/rolling_orders.sql": (
                "MODEL (materialized table, run_despite_unchanged 30d);\n\n"
                "SELECT order_id, amount_cents, CURRENT_TIMESTAMP AS refreshed_at "
                'FROM __source("raw_orders")\n'
            ),
            "models/orders_mart.sql": (
                "MODEL (materialized table);\n\n"
                "SELECT order_id, amount_cents / 100.0 AS amount_dollars, refreshed_at "
                'FROM __ref("rolling_orders")\n'
            ),
        },
    )
    initial_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )

    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    assert "Plan ready (2 selected)" in build_result.stdout
    assert "table     rolling_orders" in build_result.stdout
    assert "orders_mart" in build_result.stdout
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT amount_dollars FROM orders_mart ORDER BY order_id",
    ) == [(test_case.expected_changed_amount_dollars,)]


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlyStateBuildE2ETestCase(
            description=(
                "scoped run_despite_unchanged build leaves downstream stale then catches up"
            ),
            project_name="direct_build_run_despite_unchanged_scoped",
            initial_amount_cents=100,
            changed_amount_cents=100,
            expected_initial_amount_dollars=1.0,
            expected_changed_amount_dollars=1.0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_scoped_run_despite_unchanged_build_when_building_later_then_downstream_catches_up(
    test_case: DirectChangesOnlyStateBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": (
                f'name = "{test_case.project_name}"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    expression: SELECT 1 AS order_id, 100 AS amount_cents\n"
            ),
            "models/rolling_orders.sql": (
                "MODEL (materialized table, run_despite_unchanged always);\n\n"
                "SELECT order_id, amount_cents, CURRENT_TIMESTAMP AS refreshed_at "
                'FROM __source("raw_orders")\n'
            ),
            "models/orders_mart.sql": (
                "MODEL (materialized table);\n\n"
                "SELECT order_id, amount_cents / 100.0 AS amount_dollars, refreshed_at "
                'FROM __ref("rolling_orders")\n'
            ),
        },
    )
    initial_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr

    scoped_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "rolling_orders"),
        project_dir=project_dir,
    )
    assert scoped_result.returncode == 0, scoped_result.stdout + scoped_result.stderr
    assert "Plan ready (1 selected)" in scoped_result.stdout

    later_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert later_result.returncode == 0, later_result.stdout + later_result.stderr
    assert "Plan ready (2 selected)" in later_result.stdout
    assert "orders_mart" in later_result.stdout
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT amount_dollars FROM orders_mart ORDER BY order_id",
    ) == [(test_case.expected_changed_amount_dollars,)]


@pytest.mark.parametrize(
    "test_case",
    [
        DirectReuseFromBuildE2ETestCase(
            description="dev build reuses prod table relation",
            project_name="direct_reuse_from_build_copies_prod_relation",
            expected_prod_build_exit_code=0,
            expected_dev_build_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_reuse_from_target_when_building_dev_then_copies_prod_relation(
    test_case: DirectReuseFromBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_direct_reuse_from_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    (project_dir / "sqlbuild_local.toml").write_text('target = "prod"\n', encoding="utf-8")
    prod_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert prod_result.returncode == test_case.expected_prod_build_exit_code, (
        prod_result.stdout + prod_result.stderr
    )

    prod_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT reuse_marker FROM prod.orders",
    )
    (project_dir / "sqlbuild_local.toml").write_text('target = "dev"\n', encoding="utf-8")
    dev_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert dev_result.returncode == test_case.expected_dev_build_exit_code, (
        dev_result.stdout + dev_result.stderr
    )
    assert (
        query_duckdb(
            db_path=db_path,
            sql="SELECT reuse_marker FROM dev.orders",
        )
        == prod_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DirectReuseFromBuildE2ETestCase(
            description="dev reuse_from consumes prod audit proof",
            project_name="direct_reuse_from_build_reuses_audit_proof",
            expected_prod_build_exit_code=0,
            expected_dev_build_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_reuse_from_target_with_origin_audit_proof_when_building_dev_then_marks_audit_reused(
    test_case: DirectReuseFromBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_direct_reuse_from_audit_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    execution_json_path: Path = project_dir / "target" / "dev-build.json"
    (project_dir / "sqlbuild_local.toml").write_text('target = "prod"\n', encoding="utf-8")
    prod_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert prod_result.returncode == test_case.expected_prod_build_exit_code, (
        prod_result.stdout + prod_result.stderr
    )

    execute_duckdb(db_path=db_path, sql="UPDATE prod.orders SET id = NULL")
    (project_dir / "sqlbuild_local.toml").write_text('target = "dev"\n', encoding="utf-8")
    dev_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--json-output", str(execution_json_path)),
        project_dir=project_dir,
    )
    payload: dict[str, object] = json.loads(execution_json_path.read_text(encoding="utf-8"))
    checks: list[dict[str, object]] = payload["checks"]  # type: ignore[assignment]

    assert dev_result.returncode == test_case.expected_dev_build_exit_code, (
        dev_result.stdout + dev_result.stderr
    )
    assert "proof reused" in dev_result.stdout
    assert query_duckdb(db_path=db_path, sql="SELECT id FROM dev.orders") == [(None,)]
    assert checks[0]["kind"] == "audit"
    assert checks[0]["reused"] is True


@pytest.mark.parametrize(
    "test_case",
    [
        DirectReuseFromBuildE2ETestCase(
            description="dev build prepares custom materialization from prod baseline",
            project_name="direct_reuse_from_custom_prepare_version",
            expected_prod_build_exit_code=0,
            expected_dev_build_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_custom_reuse_from_target_when_building_dev_then_prepare_version_seeds_baseline(
    test_case: DirectReuseFromBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_direct_custom_reuse_from_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    (project_dir / "sqlbuild_local.toml").write_text('target = "prod"\n', encoding="utf-8")
    prod_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert prod_result.returncode == test_case.expected_prod_build_exit_code, (
        prod_result.stdout + prod_result.stderr
    )
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT id, amount_cents, prepare_marker, materialize_marker "
            "FROM prod.orders ORDER BY id"
        ),
    ) == [(1, 10, "fresh", "finalized"), (2, 20, "fresh", "finalized")]

    (project_dir / "sqlbuild_local.toml").write_text('target = "dev"\n', encoding="utf-8")
    dev_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert dev_result.returncode == test_case.expected_dev_build_exit_code, (
        dev_result.stdout + dev_result.stderr
    )
    assert (
        "merge_by_id (custom) (hard-copy seeded reuse from reuse origin target prod)"
        in dev_result.stdout
    )
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT id, amount_cents, prepare_marker, materialize_marker "
            "FROM dev.orders ORDER BY id"
        ),
    ) == [
        (1, 10, "prepared_from_prod", "finalized"),
        (2, 20, "prepared_from_prod", "finalized"),
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        DirectReuseFromBuildE2ETestCase(
            description="multi-schema reuse_from uses per-model origin state",
            project_name="direct_reuse_from_multi_schema_to_single_dev",
            expected_prod_build_exit_code=0,
            expected_dev_build_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_multi_schema_reuse_from_when_building_dev_then_uses_per_model_origin_state(
    test_case: DirectReuseFromBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_direct_reuse_from_multi_schema_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    execution_json_path: Path = project_dir / "target" / "dev-build.json"
    (project_dir / "sqlbuild_local.toml").write_text('target = "prod"\n', encoding="utf-8")
    prod_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert prod_result.returncode == test_case.expected_prod_build_exit_code, (
        prod_result.stdout + prod_result.stderr
    )
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT node_name, target_schema, target_name "
            "FROM prod_staging._sqlbuild_fingerprints WHERE node_name = 'stg_orders'"
        ),
    ) == [("stg_orders", "prod_staging", "stg_orders")]
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT node_name, target_schema, target_name "
            "FROM prod_marts._sqlbuild_fingerprints WHERE node_name = 'fact_orders'"
        ),
    ) == [("fact_orders", "prod_marts", "fact_orders")]
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT source_name, data_version FROM prod_staging._sqlbuild_source_freshness",
    ) == [("raw_orders", "1")]
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT source_name, data_version FROM prod_marts._sqlbuild_source_freshness",
    ) == [("raw_orders", "1")]

    (project_dir / "sqlbuild_local.toml").write_text('target = "dev"\n', encoding="utf-8")
    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan"), project_dir=project_dir
    )
    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    assert "hard-copy reuse from reuse origin target prod" in plan_result.stdout
    assert "prod_staging" not in plan_result.stdout
    assert "prod_marts" not in plan_result.stdout

    plan_json_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--json"), project_dir=project_dir
    )
    assert plan_json_result.returncode == 0, plan_json_result.stdout + plan_json_result.stderr
    plan_payload: dict[str, object] = json.loads(plan_json_result.stdout)
    plan_models: dict[str, dict[str, object]] = {
        str(model["name"]): model
        for model in plan_payload["models"]  # type: ignore[index]
    }
    assert plan_models["stg_orders"]["relation_reuse"] == {
        "kind": "complete_relation_reuse",
        "reuse_from_target": "prod",
        "origin_relation": "prod_staging.stg_orders",
        "hard_copy": True,
    }
    assert plan_models["fact_orders"]["relation_reuse"] == {
        "kind": "complete_relation_reuse",
        "reuse_from_target": "prod",
        "origin_relation": "prod_marts.fact_orders",
        "hard_copy": True,
    }

    dev_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--json-output", str(execution_json_path)),
        project_dir=project_dir,
    )
    assert dev_result.returncode == test_case.expected_dev_build_exit_code, (
        dev_result.stdout + dev_result.stderr
    )
    assert "hard-copy reuse from reuse origin target prod" in dev_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id, amount_dollars FROM dev.fact_orders",
    ) == [(1, 1.25)]
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT node_name, target_schema, target_name FROM dev._sqlbuild_fingerprints "
            "WHERE node_name IN ('stg_orders', 'fact_orders') ORDER BY node_name"
        ),
    ) == [
        ("fact_orders", "dev", "fact_orders"),
        ("stg_orders", "dev", "stg_orders"),
    ]
    execution_payload: dict[str, object] = json.loads(execution_json_path.read_text())
    execution_assets: dict[str, dict[str, object]] = {
        str(asset["name"]): asset
        for asset in execution_payload["assets"]  # type: ignore[index]
    }
    assert execution_assets["stg_orders"]["relation_reuse"] == {
        "kind": "complete_relation_reuse",
        "reuse_from_target": "prod",
        "origin_relation": "prod_staging.stg_orders",
        "hard_copy": True,
    }
    assert execution_assets["fact_orders"]["relation_reuse"] == {
        "kind": "complete_relation_reuse",
        "reuse_from_target": "prod",
        "origin_relation": "prod_marts.fact_orders",
        "hard_copy": True,
    }
    steady_state_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert steady_state_result.returncode == 0, (
        steady_state_result.stdout + steady_state_result.stderr
    )
    assert "Plan ready (0 selected)" in steady_state_result.stdout
    assert "Skipped current models (3 already up to date)" in steady_state_result.stdout
    assert "Execution  sqb build" not in steady_state_result.stdout
    assert "TOTAL=0" not in steady_state_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DirectReuseFromBuildE2ETestCase(
            description="scoped reuse_from leaves downstream stale then catches up",
            project_name="direct_reuse_from_scoped_then_later",
            expected_prod_build_exit_code=0,
            expected_dev_build_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_scoped_reuse_from_build_when_building_later_then_downstream_catches_up(
    test_case: DirectReuseFromBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_direct_reuse_from_multi_schema_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    (project_dir / "sqlbuild_local.toml").write_text('target = "prod"\n', encoding="utf-8")
    prod_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert prod_result.returncode == test_case.expected_prod_build_exit_code, (
        prod_result.stdout + prod_result.stderr
    )
    prod_changes_only_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert prod_changes_only_result.returncode == 0, (
        prod_changes_only_result.stdout + prod_changes_only_result.stderr
    )

    (project_dir / "sqlbuild_local.toml").write_text('target = "dev"\n', encoding="utf-8")
    scoped_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "stg_orders"),
        project_dir=project_dir,
    )
    assert scoped_result.returncode == 0, scoped_result.stdout + scoped_result.stderr
    assert "Plan ready (1 selected)" in scoped_result.stdout
    assert "stg_orders" in scoped_result.stdout
    assert "hard-copy reuse from reuse origin target prod" in scoped_result.stdout
    assert "Remaining stale" in scoped_result.stdout
    assert "int_orders" in scoped_result.stdout
    assert "fact_orders" in scoped_result.stdout
    assert table_exists(db_path=db_path, schema="dev", table_name="stg_orders")
    assert not table_exists(db_path=db_path, schema="dev", table_name="int_orders")
    assert not table_exists(db_path=db_path, schema="dev", table_name="fact_orders")
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT node_name, target_schema, target_name FROM dev._sqlbuild_fingerprints "
            "ORDER BY node_name"
        ),
    ) == [("stg_orders", "dev", "stg_orders")]

    later_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )

    assert later_result.returncode == test_case.expected_dev_build_exit_code, (
        later_result.stdout + later_result.stderr
    )
    assert "Plan ready (2 selected)" in later_result.stdout
    assert "hard-copy reuse from reuse origin target prod" in later_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id, amount_dollars FROM dev.fact_orders",
    ) == [(1, 1.25)]
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT node_name, target_schema, target_name FROM dev._sqlbuild_fingerprints "
            "ORDER BY node_name"
        ),
    ) == [
        ("fact_orders", "dev", "fact_orders"),
        ("int_orders", "dev", "int_orders"),
        ("stg_orders", "dev", "stg_orders"),
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        DirectReuseFromBuildE2ETestCase(
            description="selector expansion and selector kinds reuse scoped models",
            project_name="direct_reuse_from_selector_matrix",
            expected_prod_build_exit_code=0,
            expected_dev_build_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_reuse_from_when_selecting_by_expansion_tag_and_path_then_reuses_scope(
    test_case: DirectReuseFromBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_direct_reuse_from_multi_schema_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    (project_dir / "sqlbuild_local.toml").write_text('target = "prod"\n', encoding="utf-8")
    prod_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert prod_result.returncode == test_case.expected_prod_build_exit_code, (
        prod_result.stdout + prod_result.stderr
    )

    (project_dir / "sqlbuild_local.toml").write_text('target = "dev"\n', encoding="utf-8")
    expanded_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "+fact_orders"),
        project_dir=project_dir,
    )
    assert expanded_result.returncode == test_case.expected_dev_build_exit_code, (
        expanded_result.stdout + expanded_result.stderr
    )
    assert "Plan ready (3 selected)" in expanded_result.stdout
    assert "hard-copy reuse from reuse origin target prod" in expanded_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id, amount_dollars FROM dev.fact_orders",
    ) == [(1, 1.25)]

    execute_duckdb(db_path=db_path, sql="DROP SCHEMA dev CASCADE")
    tag_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "+tag:marts"),
        project_dir=project_dir,
    )
    assert tag_result.returncode == test_case.expected_dev_build_exit_code, (
        tag_result.stdout + tag_result.stderr
    )
    assert "Plan ready (3 selected)" in tag_result.stdout
    assert "fact_orders" in tag_result.stdout
    assert "hard-copy reuse from reuse origin target prod" in tag_result.stdout
    assert table_exists(db_path=db_path, schema="dev", table_name="fact_orders")
    assert table_exists(db_path=db_path, schema="dev", table_name="stg_orders")

    execute_duckdb(db_path=db_path, sql="DROP SCHEMA dev CASCADE")
    path_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "+path:models/marts"),
        project_dir=project_dir,
    )
    assert path_result.returncode == test_case.expected_dev_build_exit_code, (
        path_result.stdout + path_result.stderr
    )
    assert "Plan ready (3 selected)" in path_result.stdout
    assert "fact_orders" in path_result.stdout
    assert "hard-copy reuse from reuse origin target prod" in path_result.stdout
    assert table_exists(db_path=db_path, schema="dev", table_name="fact_orders")
    assert table_exists(db_path=db_path, schema="dev", table_name="stg_orders")


@pytest.mark.parametrize(
    "test_case",
    [
        DirectReuseFromBuildE2ETestCase(
            description="full refresh bypasses reuse_from execution",
            project_name="direct_reuse_from_full_refresh_bypass",
            expected_prod_build_exit_code=0,
            expected_dev_build_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_reuse_from_when_full_refreshing_then_builds_without_reuse(
    test_case: DirectReuseFromBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_direct_reuse_from_multi_schema_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    (project_dir / "sqlbuild_local.toml").write_text('target = "prod"\n', encoding="utf-8")
    prod_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert prod_result.returncode == test_case.expected_prod_build_exit_code, (
        prod_result.stdout + prod_result.stderr
    )

    (project_dir / "sqlbuild_local.toml").write_text('target = "dev"\n', encoding="utf-8")
    dev_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--full-refresh"), project_dir=project_dir
    )
    assert dev_result.returncode == test_case.expected_dev_build_exit_code, (
        dev_result.stdout + dev_result.stderr
    )
    assert "reuse origin target" not in dev_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id, amount_dollars FROM dev.fact_orders",
    ) == [(1, 1.25)]


@pytest.mark.parametrize(
    "test_case",
    [
        DirectReuseFromBuildE2ETestCase(
            description="function change prevents unsafe reuse",
            project_name="direct_reuse_from_function_change_builds_dev",
            expected_prod_build_exit_code=0,
            expected_dev_build_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_function_change_with_reuse_from_when_building_dev_then_builds_expected_version(
    test_case: DirectReuseFromBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": (
                f'name = "{test_case.project_name}"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.prod]\n"
                'schema = "prod"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n'
                'reuse_from = "prod"\n'
                "reuse_hard_copy = true\n"
            ),
            "functions/sql/order_score.sql": (
                "FUNCTION (arguments (amount INTEGER), returns INTEGER, replay_on_change full);\n\n"
                "amount + 1\n"
            ),
            "models/orders.sql": (
                'MODEL (materialized table);\n\nSELECT __udf("order_score")(100) AS score\n'
            ),
        },
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    (project_dir / "sqlbuild_local.toml").write_text('target = "prod"\n', encoding="utf-8")
    prod_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert prod_result.returncode == test_case.expected_prod_build_exit_code, (
        prod_result.stdout + prod_result.stderr
    )

    (project_dir / "functions" / "sql" / "order_score.sql").write_text(
        "FUNCTION (arguments (amount INTEGER), returns INTEGER, replay_on_change full);\n\n"
        "amount + 2\n",
        encoding="utf-8",
    )
    (project_dir / "sqlbuild_local.toml").write_text('target = "dev"\n', encoding="utf-8")
    dev_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert dev_result.returncode == test_case.expected_dev_build_exit_code, (
        dev_result.stdout + dev_result.stderr
    )
    assert "reuse origin target" not in dev_result.stdout
    assert query_duckdb(db_path=db_path, sql="SELECT score FROM dev.orders") == [(102,)]


@pytest.mark.parametrize(
    "test_case",
    [
        DirectReuseFromBuildE2ETestCase(
            description="source freshness change prevents complete table reuse",
            project_name="direct_reuse_from_source_freshness_change_builds_dev",
            expected_prod_build_exit_code=0,
            expected_dev_build_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_source_freshness_change_with_reuse_from_when_building_dev_then_builds_current_data(
    test_case: DirectReuseFromBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": (
                f'name = "{test_case.project_name}"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.prod]\n"
                'schema = "prod"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n'
                'reuse_from = "prod"\n'
                "reuse_hard_copy = true\n"
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    schema: raw\n"
                "    table: raw_orders\n"
                "    freshness:\n"
                "      strategy: sql\n"
                "      type: integer\n"
                "      query: SELECT data_version FROM freshness_control\n"
            ),
            "models/orders.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT order_id, amount_cents FROM __source("raw_orders")\n'
            ),
        },
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE SCHEMA raw; "
            "CREATE TABLE raw.raw_orders AS SELECT 1 AS order_id, 100 AS amount_cents; "
            "CREATE TABLE freshness_control AS SELECT 1 AS data_version"
        ),
    )
    (project_dir / "sqlbuild_local.toml").write_text('target = "prod"\n', encoding="utf-8")
    prod_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert prod_result.returncode == test_case.expected_prod_build_exit_code, (
        prod_result.stdout + prod_result.stderr
    )

    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE OR REPLACE TABLE raw.raw_orders AS "
            "SELECT 1 AS order_id, 200 AS amount_cents; "
            "UPDATE freshness_control SET data_version = 2"
        ),
    )
    (project_dir / "sqlbuild_local.toml").write_text('target = "dev"\n', encoding="utf-8")
    dev_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert dev_result.returncode == test_case.expected_dev_build_exit_code, (
        dev_result.stdout + dev_result.stderr
    )
    assert "reuse origin target" not in dev_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id, amount_cents FROM dev.orders",
    ) == [(1, 200)]


@pytest.mark.parametrize(
    "test_case",
    [
        DirectReuseFromBuildE2ETestCase(
            description="prod version mismatch falls back to dev build",
            project_name="direct_reuse_from_version_mismatch_builds_dev",
            expected_prod_build_exit_code=0,
            expected_dev_build_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_prod_version_mismatch_with_reuse_from_when_building_dev_then_builds_destination(
    test_case: DirectReuseFromBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_direct_reuse_from_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    model_path: Path = project_dir / "models" / "orders.sql"
    model_path.write_text(
        "MODEL (materialized table);\n\nSELECT 1 AS order_id, 100 AS amount_cents\n",
        encoding="utf-8",
    )
    (project_dir / "sqlbuild_local.toml").write_text('target = "prod"\n', encoding="utf-8")
    prod_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert prod_result.returncode == test_case.expected_prod_build_exit_code, (
        prod_result.stdout + prod_result.stderr
    )

    model_path.write_text(
        "MODEL (materialized table);\n\nSELECT 1 AS order_id, 200 AS amount_cents\n",
        encoding="utf-8",
    )
    (project_dir / "sqlbuild_local.toml").write_text('target = "dev"\n', encoding="utf-8")
    dev_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert dev_result.returncode == test_case.expected_dev_build_exit_code, (
        dev_result.stdout + dev_result.stderr
    )
    assert "reuse origin target" not in dev_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id, amount_cents FROM dev.orders",
    ) == [(1, 200)]


@pytest.mark.parametrize(
    "test_case",
    [
        DirectReuseFromBuildE2ETestCase(
            description="missing prod relation falls back to dev build",
            project_name="direct_reuse_from_missing_relation_builds_dev",
            expected_prod_build_exit_code=0,
            expected_dev_build_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_prod_relation_missing_with_reuse_from_when_building_dev_then_builds_destination(
    test_case: DirectReuseFromBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_direct_reuse_from_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    (project_dir / "models" / "orders.sql").write_text(
        "MODEL (materialized table);\n\nSELECT 1 AS order_id, 100 AS amount_cents\n",
        encoding="utf-8",
    )
    (project_dir / "sqlbuild_local.toml").write_text('target = "prod"\n', encoding="utf-8")
    prod_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert prod_result.returncode == test_case.expected_prod_build_exit_code, (
        prod_result.stdout + prod_result.stderr
    )
    execute_duckdb(db_path=db_path, sql="DROP TABLE prod.orders")

    (project_dir / "sqlbuild_local.toml").write_text('target = "dev"\n', encoding="utf-8")
    dev_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert dev_result.returncode == test_case.expected_dev_build_exit_code, (
        dev_result.stdout + dev_result.stderr
    )
    assert "reuse origin target" not in dev_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id, amount_cents FROM dev.orders",
    ) == [(1, 100)]


@pytest.mark.parametrize(
    "test_case",
    [
        DirectReuseFromBuildE2ETestCase(
            description="inaccessible prod fingerprint state fails clearly",
            project_name="direct_reuse_from_missing_fingerprint_state_fails",
            expected_prod_build_exit_code=0,
            expected_dev_build_exit_code=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_prod_fingerprint_state_missing_with_reuse_from_when_building_dev_then_it_fails(
    test_case: DirectReuseFromBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_direct_reuse_from_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
    )
    (project_dir / "sqlbuild_local.toml").write_text('target = "dev"\n', encoding="utf-8")

    dev_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert dev_result.returncode == test_case.expected_dev_build_exit_code
    output: str = dev_result.stdout + dev_result.stderr
    assert "target 'dev' has reuse_from = 'prod'" in output
    assert "cannot read fingerprint state for reuse origin schema 'prod'" in output
    assert "prove the reuse origin relation matches the expected version" in output


@pytest.mark.parametrize(
    "test_case",
    [
        DirectReuseFromBuildE2ETestCase(
            description="dev build reuses prod snapshot relation and catches up",
            project_name="direct_reuse_from_build_seeds_snapshot",
            expected_prod_build_exit_code=0,
            expected_dev_build_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_reuse_from_target_when_building_dev_snapshot_then_seeds_and_catches_up(
    test_case: DirectReuseFromBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_direct_snapshot_reuse_from_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    (project_dir / "sqlbuild_local.toml").write_text('target = "prod"\n', encoding="utf-8")
    prod_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert prod_result.returncode == test_case.expected_prod_build_exit_code, (
        prod_result.stdout + prod_result.stderr
    )

    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE OR REPLACE TABLE raw.raw_accounts AS "
            "SELECT 1 AS account_id, 'pro' AS plan, "
            "TIMESTAMP '2024-01-03 00:00:00' AS updated_at "
            "UNION ALL SELECT 2 AS account_id, 'basic' AS plan, "
            "TIMESTAMP '2024-01-02 00:00:00' AS updated_at"
        ),
    )
    (project_dir / "sqlbuild_local.toml").write_text('target = "dev"\n', encoding="utf-8")
    dev_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert dev_result.returncode == test_case.expected_dev_build_exit_code, (
        dev_result.stdout + dev_result.stderr
    )
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT account_id, plan, CAST(valid_from AS VARCHAR), CAST(valid_to AS VARCHAR) "
            "FROM dev.account_snapshot ORDER BY account_id, valid_from"
        ),
    ) == [
        (1, "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
        (1, "pro", "2024-01-03 00:00:00", None),
        (2, "basic", "2024-01-02 00:00:00", None),
    ]
