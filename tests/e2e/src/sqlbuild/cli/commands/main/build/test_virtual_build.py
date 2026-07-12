from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    VirtualBuildE2ETestCase,
    VirtualBuildSelectionGuardE2ETestCase,
    VirtualConcurrentBuildE2ETestCase,
    VirtualCustomMaterializationE2ETestCase,
    VirtualExplicitCheckpointRollbackE2ETestCase,
    VirtualNodeResultFailureStateE2ETestCase,
    VirtualNodeResultStateE2ETestCase,
    VirtualPartialRollbackE2ETestCase,
    VirtualPromoteE2ETestCase,
    VirtualPythonBuildE2ETestCase,
    VirtualPythonHooksBuildE2ETestCase,
    VirtualPythonIdentityBuildE2ETestCase,
    VirtualRollbackE2ETestCase,
    VirtualSeedBuildE2ETestCase,
    VirtualSeedGapE2ETestCase,
    VirtualSourceFreshnessBuildE2ETestCase,
    VirtualWaffleShopE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import (
    build_virtual_multi_seed_lifecycle_repo_files,
    build_virtual_seed_lifecycle_repo_files,
    build_virtual_wide_dag_repo_files,
    count_virtual_physical_versions,
    initialize_virtual_seeded_project,
    prepare_virtual_cursor_override_without_snapshot_project,
    prepare_virtual_seeded_incremental_project,
    rewrite_cursor_override_without_snapshot_model,
    rewrite_incremental_orders_model,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_virtual_plan_project_toml,
    build_virtual_plan_repo_files,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    prepare_waffle_shop,
    query_duckdb,
    run_sqb,
    table_exists,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualConcurrentBuildE2ETestCase(
            description="wide virtual DAG builds with concurrent physical schema setup",
            concurrency=8,
            expected_model_count=8,
            expected_build_fragments=("Execution  sqb build  (concurrency: 8)",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_wide_virtual_dag_when_building_concurrently_then_physical_schema_setup_is_safe(
    test_case: VirtualConcurrentBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_concurrent_schema_setup",
        repo_files=build_virtual_wide_dag_repo_files(
            model_count=test_case.expected_model_count,
        ),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--concurrency", str(test_case.concurrency)),
        project_dir=project_dir,
    )

    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    fragment: str
    for fragment in test_case.expected_build_fragments:
        assert fragment in build_result.stdout
    physical_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'dev__sqb_physical' AND table_name LIKE '%__v_%' "
            "ORDER BY table_name"
        ),
    )
    assert len(physical_rows) == test_case.expected_model_count
    logical_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id, model_name FROM dev__dev.model_08",
    )
    assert logical_rows == [(8, "model_08")]


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualBuildE2ETestCase(
            description="default VDE creates physical versions and queryable views",
            expected_build_fragments=("Virtual environment", "name: dev"),
            expected_plan_fragments=("Plan ready (0 selected)", "status: finalized"),
            expected_query_results=(("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((7,),)),),
            expected_ref_rows=(("dim_customers",), ("fact_orders",), ("stg_orders",)),
            expected_physical_version_count=3,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_default_vde_when_building_then_it_creates_physical_versions_and_views(
    test_case: VirtualBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_build_default_vde",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 7 AS id"),
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
    fragment: str
    for fragment in test_case.expected_build_fragments:
        assert fragment in build_result.stdout
    assert table_exists(
        db_path=project_dir / "warehouse.duckdb",
        schema="dev__dev",
        table_name="stg_orders",
    )
    assert table_exists(
        db_path=project_dir / "warehouse.duckdb",
        schema="dev__dev",
        table_name="fact_orders",
    )
    assert not table_exists(
        db_path=project_dir / "warehouse.duckdb",
        schema="dev__sqb_physical",
        table_name="_sqlbuild_fingerprints",
    )
    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(
            db_path=project_dir / "warehouse.duckdb",
            sql=query_sql,
        ) == list(expected_rows)
    physical_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'dev__sqb_physical' AND table_name LIKE '%__v_%' "
            "ORDER BY table_name"
        ),
    )
    assert len(physical_rows) == test_case.expected_physical_version_count
    assert all("__v_" in str(row[0]) for row in physical_rows)
    ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'model' "
            "ORDER BY node_name"
        ),
    )
    assert ref_rows == list(test_case.expected_ref_rows)
    ref_hash_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'model' "
            "ORDER BY node_name"
        ),
    )

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan"),
        project_dir=project_dir,
    )

    assert plan_result.returncode == 0, plan_result.stderr
    for fragment in test_case.expected_plan_fragments:
        assert fragment in plan_result.stdout

    repeat_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert repeat_build_result.returncode == 0, repeat_build_result.stderr
    repeat_physical_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'dev__sqb_physical' AND table_name LIKE '%__v_%' "
            "ORDER BY table_name"
        ),
    )
    assert repeat_physical_rows == physical_rows
    repeat_ref_hash_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'model' "
            "ORDER BY node_name"
        ),
    )
    assert repeat_ref_hash_rows == ref_hash_rows


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSeedBuildE2ETestCase(
            description="virtual seed build persists seed refs and reloads changed seeds",
            expected_initial_rows=((1, 100),),
            expected_changed_rows=((1, 200),),
            expected_changed_fragments=(
                "order_amounts",
                "seed_changed",
                "fact_orders",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_seed_change_when_building_changes_only_then_updates_seed_state_and_model(
    test_case: VirtualSeedBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_seed_change_build",
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
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_cents FROM dev__dev.fact_orders ORDER BY order_id",
    ) == list(test_case.expected_initial_rows)
    initial_seed_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'seed' "
            "ORDER BY node_name"
        ),
    )
    assert len(initial_seed_ref_rows) == 1

    unchanged_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert unchanged_build_result.returncode == 0, unchanged_build_result.stderr
    assert "Plan ready (0 selected)" in unchanged_build_result.stdout

    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "order_id,amount_cents\n1,200\n",
        encoding="utf-8",
    )
    changed_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert changed_build_result.returncode == 0, (
        changed_build_result.stdout + changed_build_result.stderr
    )
    fragment: str
    for fragment in test_case.expected_changed_fragments:
        assert fragment in changed_build_result.stdout, changed_build_result.stdout
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_cents FROM dev__dev.fact_orders ORDER BY order_id",
    ) == list(test_case.expected_changed_rows)
    changed_seed_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'seed' "
            "ORDER BY node_name"
        ),
    )
    assert len(changed_seed_ref_rows) == 1
    assert changed_seed_ref_rows[0][0] == "order_amounts"
    assert changed_seed_ref_rows[0][1] != initial_seed_ref_rows[0][1]


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSeedBuildE2ETestCase(
            description="two VDEs bind isolated seed physical versions",
            expected_initial_rows=((1, 100),),
            expected_changed_rows=((1, 100),),
            expected_branch_rows=((1, 200),),
            expected_changed_fragments=(),
            expected_physical_seed_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_two_virtual_environments_when_seed_differs_then_each_reads_bound_seed_version(
    test_case: VirtualSeedBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_seed_isolation",
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
    dev_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert dev_build_result.returncode == 0, dev_build_result.stdout + dev_build_result.stderr

    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "order_id,amount_cents\n1,200\n",
        encoding="utf-8",
    )
    pr_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr"),
        project_dir=project_dir,
    )
    assert pr_build_result.returncode == 0, pr_build_result.stdout + pr_build_result.stderr

    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_cents FROM dev__dev.fact_orders ORDER BY order_id",
    ) == list(test_case.expected_changed_rows)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_cents FROM dev__pr.fact_orders ORDER BY order_id",
    ) == list(test_case.expected_branch_rows)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_cents FROM dev__dev.order_amounts ORDER BY order_id",
    ) == list(test_case.expected_changed_rows)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_cents FROM dev__pr.order_amounts ORDER BY order_id",
    ) == list(test_case.expected_branch_rows)
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT COUNT(*) FROM sqlbuild_state.physical_relations "
            "WHERE artifact_type = 'seed' AND artifact_name = 'order_amounts'"
        ),
    ) == [(test_case.expected_physical_seed_count,)]


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSeedBuildE2ETestCase(
            description="second VDE uses existing physical seed artifact",
            expected_initial_rows=((1, 100),),
            expected_changed_rows=((1, 100),),
            expected_changed_fragments=("order_amounts", "SKIP=1"),
            expected_physical_seed_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_second_vde_when_seed_version_exists_then_uses_existing_physical_seed(
    test_case: VirtualSeedBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_seed_existing_artifact",
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
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0

    pr_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr"),
        project_dir=project_dir,
    )

    assert pr_build_result.returncode == 0, pr_build_result.stdout + pr_build_result.stderr
    for fragment in test_case.expected_changed_fragments:
        assert fragment in pr_build_result.stdout, pr_build_result.stdout
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_cents FROM dev__pr.fact_orders ORDER BY order_id",
    ) == list(test_case.expected_changed_rows)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_cents FROM dev__pr.order_amounts ORDER BY order_id",
    ) == list(test_case.expected_initial_rows)
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT COUNT(*) FROM sqlbuild_state.physical_relations "
            "WHERE artifact_type = 'seed' AND artifact_name = 'order_amounts'"
        ),
    ) == [(test_case.expected_physical_seed_count,)]


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSeedBuildE2ETestCase(
            description="explicit model selection updates stale upstream seed artifact",
            expected_initial_rows=((1, 100),),
            expected_changed_rows=((1, 200),),
            expected_changed_fragments=("order_amounts", "fact_orders"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_explicit_model_selection_when_upstream_seed_changed_then_model_reads_new_seed(
    test_case: VirtualSeedBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_explicit_model_with_changed_seed",
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
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_cents FROM dev__dev.fact_orders ORDER BY order_id",
    ) == list(test_case.expected_initial_rows)

    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "order_id,amount_cents\n1,200\n",
        encoding="utf-8",
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "fact_orders"),
        project_dir=project_dir,
    )

    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    for fragment in test_case.expected_changed_fragments:
        assert fragment in build_result.stdout, build_result.stdout
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT order_id, amount_cents FROM dev__dev.fact_orders ORDER BY order_id",
    ) == list(test_case.expected_changed_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSeedGapE2ETestCase(
            description="failed virtual seed reload leaves seed ref unchanged",
            expected_fragments=("order_amounts", "FAIL", "Completed with errors."),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_seed_load_failure_when_building_changes_only_then_seed_state_is_unchanged(
    test_case: VirtualSeedGapE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_seed_failure_build",
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
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stderr
    initial_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert initial_build_result.returncode == 0, (
        initial_build_result.stdout + initial_build_result.stderr
    )
    initial_seed_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name, version_hash FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'seed' ORDER BY node_name"
        ),
    )

    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "order_id,amount_cents\n1,not_an_integer\n",
        encoding="utf-8",
    )
    failed_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert failed_build_result.returncode == 1, (
        failed_build_result.stdout + failed_build_result.stderr
    )
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in failed_build_result.stdout, failed_build_result.stdout
    assert (
        query_duckdb(
            db_path=project_dir / "state.duckdb",
            sql=(
                "SELECT node_name, version_hash FROM sqlbuild_state.virtual_environment_node_refs "
                "WHERE virtual_environment_name = 'dev' AND node_type = 'seed' "
                "ORDER BY node_name"
            ),
        )
        == initial_seed_ref_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSeedGapE2ETestCase(
            description="virtual seed JSON includes seed reasons",
            expected_fragments=("order_amounts", "config_changed"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_seed_change_when_plan_and_build_json_then_seed_reason_is_reported(
    test_case: VirtualSeedGapE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_seed_json_build",
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
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "order_id,amount_cents\n1,200\n", encoding="utf-8"
    )

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("plan", "--json"), project_dir=project_dir
    )
    assert plan_result.returncode == 0, plan_result.stderr
    plan_payload: dict[str, object] = json.loads(plan_result.stdout)
    plan_seeds: list[dict[str, object]] = list(plan_payload["seeds"])
    expected_seed_name, expected_seed_reason = test_case.expected_fragments
    assert plan_seeds == [
        {
            "name": expected_seed_name,
            "reason": expected_seed_reason,
            "qualified_name": "dev.order_amounts",
        }
    ]

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("build", "--json"), project_dir=project_dir
    )
    assert build_result.returncode == 0, build_result.stderr
    build_payload: dict[str, object] = json.loads(build_result.stdout)
    seed_assets: list[dict[str, object]] = [
        dict(asset) for asset in build_payload["assets"] if dict(asset).get("kind") == "seed"
    ]
    assert seed_assets[0]["name"] == expected_seed_name
    assert seed_assets[0]["reason"] == expected_seed_reason


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSeedGapE2ETestCase(
            description="virtual seed schema change reloads seed and model",
            expected_fragments=(
                "Plan ready (2 selected)",
                "order_amounts",
                "seed_changed",
                "fact_orders",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_seed_schema_change_when_building_changes_only_then_reloads_seed_and_model(
    test_case: VirtualSeedGapE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_seed_schema_change_build",
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
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "seeds" / "schema.yml").write_text(
        "seeds:\n"
        "  - name: order_amounts\n"
        "    columns:\n"
        "      - name: order_id\n"
        "        type: INTEGER\n"
        "      - name: amount_cents\n"
        "        type: BIGINT\n",
        encoding="utf-8",
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout, result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSeedGapE2ETestCase(
            description="multi seed virtual graph selects only changed seed closure",
            expected_fragments=("Plan ready (2 selected)", "order_amounts", "fact_orders"),
            unexpected_fragments=("country_codes", "dim_countries"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_multi_seed_graph_when_one_seed_changes_then_only_its_closure_is_selected(
    test_case: VirtualSeedGapE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_multi_seed_change_build",
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
                "  - name: country_codes\n"
                "    columns:\n"
                "      - name: country_code\n"
                "        type: TEXT\n"
            ),
            "seeds/order_amounts.csv": "order_id,amount_cents\n1,100\n",
            "seeds/country_codes.csv": "country_code\nUS\n",
            "models/fact_orders.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT order_id, amount_cents FROM __seed("order_amounts")\n'
            ),
            "models/dim_countries.sql": (
                'MODEL (materialized table);\n\nSELECT country_code FROM __seed("country_codes")\n'
            ),
        },
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "order_id,amount_cents\n1,200\n", encoding="utf-8"
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan"), project_dir=project_dir
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout, result.stdout
    for fragment in test_case.unexpected_fragments:
        assert fragment not in result.stdout, result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSeedGapE2ETestCase(
            description="virtual model change with current seed does not reload seed",
            expected_fragments=("Plan ready (1 selected)", "fact_orders"),
            unexpected_fragments=("Seeds (", "seed      order_amounts"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_model_change_with_current_seed_when_building_then_seed_is_not_reloaded(
    test_case: VirtualSeedGapE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_model_change_current_seed_build",
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
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "models" / "fact_orders.sql").write_text(
        "MODEL (materialized table);\n\n"
        "SELECT order_id, amount_cents, amount_cents / 100.0 AS amount_dollars "
        'FROM __seed("order_amounts")\n',
        encoding="utf-8",
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout, result.stdout
    for fragment in test_case.unexpected_fragments:
        assert fragment not in result.stdout, result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPythonHooksBuildE2ETestCase(
            description="virtual build executes discovered Python lifecycle hook",
            expected_exit_code=0,
            expected_model_rows=((7,),),
            expected_hook_log_rows=(("fact_orders", "post_hooks"),),
            expected_identity_rows=(("hook", "log_virtual_hook"),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_build_with_python_hooks_when_building_then_hooks_execute(
    test_case: VirtualPythonHooksBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_python_hooks_build",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "hooks/lifecycle.py": dedent(
                """
                from sqlbuild.hooks import hook


                @hook
                def log_virtual_hook(ctx):
                    ctx.execute_sql(
                        "CREATE TABLE main.virtual_hook_log AS "
                        f"SELECT '{ctx.model_name}' AS model_name, '{ctx.phase}' AS phase"
                    )
                """
            ).strip()
            + "\n",
            "models/fact_orders.sql": dedent(
                """
                MODEL (
                  materialized table,
                  post_hooks [python("log_virtual_hook")]
                );

                SELECT 7 AS id
                """
            ).strip()
            + "\n",
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
    db_path: Path = project_dir / "warehouse.duckdb"

    assert build_result.returncode == test_case.expected_exit_code, build_result.stderr
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_model_rows)
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT model_name, phase FROM main.virtual_hook_log",
    ) == list(test_case.expected_hook_log_rows)
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_type, node_name "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE node_type IN ('task', 'loader', 'asset', 'check', 'hook') "
            "ORDER BY node_type, node_name"
        ),
    ) == list(test_case.expected_identity_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessBuildE2ETestCase(
            description="unchanged source freshness skips and changed freshness reruns downstream",
            expected_initial_rows=((7,),),
            expected_updated_rows=((8,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_source_freshness_when_building_then_skips_until_data_version_changes(
    test_case: VirtualSourceFreshnessBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_source_freshness_build",
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

    first_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert first_build_result.returncode == 0, first_build_result.stderr
    first_version_count: int = count_virtual_physical_versions(project_dir=project_dir)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_initial_rows)

    unchanged_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert unchanged_build_result.returncode == 0, unchanged_build_result.stderr
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count

    unchanged_changes_only_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert unchanged_changes_only_build_result.returncode == 0, (
        unchanged_changes_only_build_result.stderr
    )
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count

    explicit_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "fact_orders", "--force"),
        project_dir=project_dir,
    )
    assert explicit_build_result.returncode == 0, explicit_build_result.stderr
    assert "fact_orders" in explicit_build_result.stdout
    assert "OK" in explicit_build_result.stdout

    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="UPDATE raw.raw_orders SET id = 8, data_version = 2",
    )
    changed_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert changed_build_result.returncode == 0, changed_build_result.stderr
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count + 1
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_updated_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessBuildE2ETestCase(
            description="virtual changes-only builds runtime stale table and downstream",
            expected_initial_rows=((7,),),
            expected_updated_rows=((7,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_run_despite_unchanged_when_building_changes_only_then_builds_downstream(
    test_case: VirtualSourceFreshnessBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_build_run_despite_unchanged",
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
                      column: order_ts
                      type: timestamp
                """
            ).strip()
            + "\n",
            "models/rolling_orders.sql": (
                "MODEL (materialized table, run_despite_unchanged 30d);\n\n"
                'SELECT id, order_ts FROM __source("raw_orders")\n'
            ),
            "models/orders_mart.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __ref("rolling_orders")\n'
            ),
        },
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=dedent(
            """
            CREATE SCHEMA raw;
            CREATE TABLE raw.raw_orders (id INTEGER, order_ts TIMESTAMP);
            INSERT INTO raw.raw_orders VALUES (7, CURRENT_TIMESTAMP);
            """
        ).strip(),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    first_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert first_build_result.returncode == 0, first_build_result.stderr
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.orders_mart ORDER BY id",
    ) == list(test_case.expected_initial_rows)

    changes_only_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert changes_only_result.returncode == 0, changes_only_result.stderr
    assert "rolling_orders" in changes_only_result.stdout
    assert "orders_mart" in changes_only_result.stdout
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.orders_mart ORDER BY id",
    ) == list(test_case.expected_updated_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessBuildE2ETestCase(
            description="virtual build respects timestamp source freshness lag tolerance",
            expected_initial_rows=((7,),),
            expected_updated_rows=((9,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_timestamp_lag_tolerance_when_building_then_skips_within_tolerance(
    test_case: VirtualSourceFreshnessBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_source_freshness_build_lag_tolerance",
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
    first_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert first_build_result.returncode == 0, first_build_result.stderr
    first_version_count: int = count_virtual_physical_versions(project_dir=project_dir)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_initial_rows)

    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="UPDATE raw.raw_orders SET id = 8, data_version = '2026-01-01 12:05:00'",
    )
    within_tolerance_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert within_tolerance_build_result.returncode == 0, within_tolerance_build_result.stderr
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count

    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="UPDATE raw.raw_orders SET id = 9, data_version = '2026-01-01 12:11:00'",
    )
    beyond_tolerance_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert beyond_tolerance_build_result.returncode == 0, beyond_tolerance_build_result.stderr
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count + 1
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_updated_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessBuildE2ETestCase(
            description="unknown source freshness does not skip virtual builds",
            expected_initial_rows=((7,),),
            expected_updated_rows=((8,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_source_without_freshness_when_rebuilding_then_it_does_not_skip(
    test_case: VirtualSourceFreshnessBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_unknown_source_freshness_build",
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
    first_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert first_build_result.returncode == 0, first_build_result.stderr
    first_version_count: int = count_virtual_physical_versions(project_dir=project_dir)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_initial_rows)

    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="UPDATE raw.raw_orders SET id = 8",
    )
    second_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert second_build_result.returncode == 0, second_build_result.stderr
    assert "fact_orders" in second_build_result.stdout
    assert "OK" in second_build_result.stdout
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_updated_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessBuildE2ETestCase(
            description="source freshness propagates through views to downstream tables",
            expected_initial_rows=((7,),),
            expected_updated_rows=((8,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_source_freshness_through_view_when_changed_then_downstream_table_reruns(
    test_case: VirtualSourceFreshnessBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_source_freshness_view_build",
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
    first_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert first_build_result.returncode == 0, first_build_result.stderr
    first_version_count: int = count_virtual_physical_versions(project_dir=project_dir)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_initial_rows)

    unchanged_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert unchanged_build_result.returncode == 0, unchanged_build_result.stderr
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count

    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="UPDATE raw.raw_orders SET id = 8, data_version = 2",
    )
    changed_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert changed_build_result.returncode == 0, changed_build_result.stderr
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count + 2
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_updated_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessBuildE2ETestCase(
            description="managed loader freshness does not cause spurious virtual rebuilds",
            expected_initial_rows=((7,),),
            expected_updated_rows=((7,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_managed_source_freshness_when_unchanged_then_build_skips_downstream(
    test_case: VirtualSourceFreshnessBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_managed_source_freshness_build",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml().replace(
                "[targets.dev]\n", '[targets.dev]\ndefer_sources_to = "dev"\n'
            ),
            "loaders/raw.py": (
                "from pathlib import Path\n"
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def raw_orders(ctx):\n"
                "    marker = Path(__file__).parents[1].joinpath('raw_order_id.txt')\n"
                "    return [{'id': int(marker.read_text())}]\n"
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: id\n"
                "        type: INTEGER\n"
            ),
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
        },
    )
    (project_dir / "raw_order_id.txt").write_text("7", encoding="utf-8")
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stderr
    first_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "+fact_orders"), project_dir=project_dir
    )
    assert first_build_result.returncode == 0, first_build_result.stderr
    first_version_count: int = count_virtual_physical_versions(project_dir=project_dir)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_initial_rows)

    (project_dir / "raw_order_id.txt").write_text("8", encoding="utf-8")
    unchanged_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert unchanged_build_result.returncode == 0, unchanged_build_result.stderr
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_updated_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessBuildE2ETestCase(
            description="managed configured freshness conservatively rebinds after first load",
            expected_initial_rows=((7,),),
            expected_updated_rows=((7,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_managed_source_configured_freshness_when_building_then_rebinds_safely(
    test_case: VirtualSourceFreshnessBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_managed_configured_source_freshness_build",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml().replace(
                "[targets.dev]\n", '[targets.dev]\ndefer_sources_to = "dev"\n'
            ),
            "loaders/raw.py": (
                "from pathlib import Path\n"
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def raw_orders(ctx):\n"
                "    root = Path(__file__).parents[1]\n"
                "    return [{\n"
                "        'id': int(root.joinpath('raw_order_id.txt').read_text()),\n"
                "        'data_version': int(root.joinpath('raw_data_version.txt').read_text()),\n"
                "    }]\n"
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    freshness:\n"
                "      strategy: sql\n"
                "      query: SELECT MAX(data_version) FROM dev.raw_orders\n"
                "      type: integer\n"
                "    columns:\n"
                "      - name: id\n"
                "        type: INTEGER\n"
                "      - name: data_version\n"
                "        type: INTEGER\n"
            ),
            "models/fact_orders.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
        },
    )
    (project_dir / "raw_order_id.txt").write_text("7", encoding="utf-8")
    (project_dir / "raw_data_version.txt").write_text("1", encoding="utf-8")
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stderr
    first_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "+fact_orders"), project_dir=project_dir
    )
    assert first_build_result.returncode == 0, first_build_result.stderr
    first_version_count: int = count_virtual_physical_versions(project_dir=project_dir)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_initial_rows)

    rebind_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert rebind_build_result.returncode == 0, rebind_build_result.stderr
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count + 1
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id FROM dev__dev.fact_orders ORDER BY id",
    ) == list(test_case.expected_updated_rows)

    stable_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert stable_build_result.returncode == 0, stable_build_result.stderr
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count + 1


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessBuildE2ETestCase(
            description="explicit adapter freshness fails clearly on unsupported adapter",
            expected_initial_rows=(),
            expected_updated_rows=(),
            expected_error_fragment="does not support table freshness metadata",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_adapter_freshness_when_building_then_it_fails_clearly(
    test_case: VirtualSourceFreshnessBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_unsupported_adapter_source_freshness_build",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_orders
                    schema: raw
                    table: raw_orders
                    freshness:
                      strategy: adapter
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
        sql=(
            "CREATE SCHEMA raw; "
            "CREATE TABLE raw.raw_orders (id INTEGER); "
            "INSERT INTO raw.raw_orders VALUES (7);"
        ),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stderr

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert build_result.returncode == 1
    assert test_case.expected_error_fragment is not None
    assert test_case.expected_error_fragment in (build_result.stdout + build_result.stderr)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualSourceFreshnessBuildE2ETestCase(
            description="function and source freshness changes independently rerun virtual model",
            expected_initial_rows=((False,),),
            expected_updated_rows=((True,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_source_freshness_and_function_when_each_changes_then_model_reruns(
    test_case: VirtualSourceFreshnessBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_source_freshness_function_build",
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
            "functions/sql/is_large_order.sql": (
                "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, "
                "replay_on_change full);\n\n"
                "amount > 9\n"
            ),
            "models/fact_orders.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT __udf("is_large_order")(id) AS is_large '
                'FROM __source("raw_orders")\n'
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
    first_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert first_build_result.returncode == 0, first_build_result.stderr
    first_version_count: int = count_virtual_physical_versions(project_dir=project_dir)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT is_large FROM dev__dev.fact_orders ORDER BY is_large",
    ) == list(test_case.expected_initial_rows)

    (project_dir / "functions" / "sql" / "is_large_order.sql").write_text(
        "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, replay_on_change full);\n\n"
        "amount > 5\n",
        encoding="utf-8",
    )
    function_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert function_build_result.returncode == 0, function_build_result.stderr
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count + 1
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT is_large FROM dev__dev.fact_orders ORDER BY is_large",
    ) == list(test_case.expected_updated_rows)

    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="UPDATE raw.raw_orders SET id = 4, data_version = 2",
    )
    source_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert source_build_result.returncode == 0, source_build_result.stderr
    assert count_virtual_physical_versions(project_dir=project_dir) == first_version_count + 2
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT is_large FROM dev__dev.fact_orders ORDER BY is_large",
    ) == list(test_case.expected_initial_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPythonBuildE2ETestCase(
            description="runs loader-side and read-side Python nodes",
            project_name="virtual_python_nodes_build",
            plan_command=("--no-color", "plan", "--select", "+fact_orders"),
            build_command=("--no-color", "build", "--select", "+fact_orders"),
            expected_build_exit_code=0,
            expected_plan_fragments=(
                "Python ingress (1)",
                "prepare_orders",
                "Python read-side (2)",
                "profile_fact_orders",
                "profile_raw_orders",
            ),
            expected_prepared_text="7",
            expected_profile_text="1",
            expected_source_profile_text="1",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_python_nodes_when_building_then_runs_loader_and_read_side_python(
    test_case: VirtualPythonBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_python_nodes_build"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n\n"
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n'
                'defer_sources_to = "dev"\n\n'
                "[targets.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n\n'
                "[targets.dev.state.connection]\n"
                'database = "state.duckdb"\n'
            ),
            "tasks/prepare.py": (
                "from pathlib import Path\n"
                "from sqlbuild.tasks import task\n\n"
                "@task\n"
                "def prepare_orders(ctx):\n"
                "    Path(__file__).parents[1].joinpath('prepared.txt').write_text('7')\n"
                "    return ctx.result(payload={'order_id': 7})\n"
            ),
            "loaders/raw.py": (
                "from pathlib import Path\n"
                "from sqlbuild.loaders import loader\n"
                "from tasks.prepare import prepare_orders\n\n"
                "@loader(depends_on=(prepare_orders,))\n"
                "def raw_orders(ctx):\n"
                "    marker = Path(__file__).parents[1].joinpath('prepared.txt')\n"
                "    return [{'order_id': int(marker.read_text())}]\n"
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
            "tasks/profile.py": (
                "from pathlib import Path\n"
                "from sqlbuild.refs import model, source\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=model('fact_orders'))\n"
                "def profile_fact_orders(ctx):\n"
                "    relation = ctx.relation(model('fact_orders'))\n"
                "    rows = ctx.query(f'SELECT COUNT(*) FROM {relation}').fetchall()[0][0]\n"
                "    Path(__file__).parents[1].joinpath('profile.txt').write_text(str(rows))\n"
                "    return ctx.result(payload={'rows': rows})\n"
                "\n"
                "@task(depends_on=source('raw_orders'))\n"
                "def profile_raw_orders(ctx):\n"
                "    relation = ctx.relation(source('raw_orders'))\n"
                "    rows = ctx.query(f'SELECT COUNT(*) FROM {relation}').fetchall()[0][0]\n"
                "    output = Path(__file__).parents[1].joinpath('source_profile.txt')\n"
                "    output.write_text(str(rows))\n"
                "    return ctx.result(payload={'rows': rows})\n"
            ),
        },
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.plan_command,
        project_dir=project_dir,
    )
    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    for fragment in test_case.expected_plan_fragments:
        assert fragment in plan_result.stdout

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.build_command,
        project_dir=project_dir,
    )

    assert build_result.returncode == test_case.expected_build_exit_code, (
        build_result.stdout + build_result.stderr
    )
    assert (project_dir / "prepared.txt").read_text(encoding="utf-8") == (
        test_case.expected_prepared_text
    )
    assert (project_dir / "profile.txt").read_text(encoding="utf-8") == (
        test_case.expected_profile_text
    )
    assert (project_dir / "source_profile.txt").read_text(encoding="utf-8") == (
        test_case.expected_source_profile_text
    )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualNodeResultStateE2ETestCase(
            description="persists loader task asset and check node results in virtual state",
            expected_state_rows=(
                ("dev", "asset", "publish_result", "success"),
                ("dev", "check", "check_produce_result", "success"),
                ("dev", "loader", "raw_orders", "success"),
                ("dev", "task", "produce_result", "success"),
                ("dev", "task", "summarize_loader", "success"),
            ),
            expected_asset_payload={"value": 42},
            expected_loader_text="raw_orders:raw_orders:1",
            expected_history_text="42:1",
            expected_warehouse_result_table_count=0,
            expected_build_fragments=("check_produce_result", "PASS"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_python_result_when_building_then_persists_node_results_in_state(
    test_case: VirtualNodeResultStateE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_node_results_state",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_node_results_state"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n\n"
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n\n'
                'defer_sources_to = "dev"\n\n'
                "[targets.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n\n'
                "[targets.dev.state.connection]\n"
                'database = "state.duckdb"\n'
            ),
            "loaders/orders.py": (
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def raw_orders(ctx):\n"
                "    return [{'value': 42}]\n"
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: value\n"
                "        type: INTEGER\n"
            ),
            "tasks/results.py": (
                "from pathlib import Path\n"
                "from loaders.orders import raw_orders\n"
                "from sqlbuild.refs import model\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=model('orders'))\n"
                "def produce_result(ctx):\n"
                "    return ctx.result(payload={'value': 42}, metadata={'source': 'vde'})\n"
                "\n"
                "@task(depends_on=model('orders'))\n"
                "def summarize_loader(ctx):\n"
                "    result = ctx.result_of(raw_orders)\n"
                "    history = ctx.results_of(raw_orders, limit=1)\n"
                "    output = Path(__file__).parents[1].joinpath('loader_result.txt')\n"
                "    output.write_text(\n"
                "        f\"{result.metadata['loader_name']}:{result.metadata['source_name']}:\"\n"
                "        f\"{result.metadata['rows_loaded']}\"\n"
                "    )\n"
                "    history_output = Path(__file__).parents[1].joinpath('history_result.txt')\n"
                "    history_output.write_text(\n"
                "        f\"{ctx.result_of(produce_result).payload['value']}:{len(history)}\"\n"
                "    )\n"
                "    return ctx.result(metadata={'summarized': True})\n"
            ),
            "assets/results.py": (
                "from sqlbuild.assets import asset\n"
                "from tasks.results import produce_result\n\n"
                "@asset(depends_on=produce_result)\n"
                "def publish_result(ctx):\n"
                "    payload = ctx.result_of(produce_result).payload\n"
                "    return ctx.result(payload=payload, materialized=True)\n"
            ),
            "models/orders.sql": (
                'MODEL (materialized table);\n\nSELECT value FROM __source("raw_orders")\n'
            ),
            "checks/results.py": (
                "from sqlbuild.checks import check\n"
                "from assets.results import publish_result\n"
                "from tasks.results import produce_result, summarize_loader\n\n"
                "@check(depends_on=(publish_result, summarize_loader))\n"
                "def check_produce_result(ctx):\n"
                "    return (\n"
                "        ctx.result_of(produce_result).payload['value'] == 42\n"
                "        and ctx.result_of(publish_result).payload['value'] == 42\n"
                "    )\n"
            ),
        },
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "orders"),
        project_dir=project_dir,
    )

    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    for fragment in test_case.expected_build_fragments:
        assert fragment in build_result.stdout
    state_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT virtual_environment_name, node_type, node_name, status "
            "FROM sqlbuild_state.node_results "
            "WHERE node_name IN ("
            "'raw_orders', 'produce_result', 'summarize_loader', "
            "'publish_result', 'check_produce_result') "
            "ORDER BY node_type, node_name"
        ),
    )
    assert state_rows == list(test_case.expected_state_rows)
    asset_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT payload_json_b64, materialized FROM sqlbuild_state.node_results "
            "WHERE node_type = 'asset' AND node_name = 'publish_result'"
        ),
    )
    assert len(asset_rows) == 1
    assert json.loads(base64.b64decode(str(asset_rows[0][0])).decode("utf-8")) == (
        test_case.expected_asset_payload
    )
    assert asset_rows[0][1] == "true"
    assert (project_dir / "loader_result.txt").read_text(encoding="utf-8") == (
        test_case.expected_loader_text
    )
    assert (project_dir / "history_result.txt").read_text(encoding="utf-8") == (
        test_case.expected_history_text
    )
    warehouse_result_table_count: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = '_sqlbuild_node_results'"
        ),
    )
    assert warehouse_result_table_count == [(test_case.expected_warehouse_result_table_count,)]


@pytest.mark.parametrize(
    "test_case",
    (
        VirtualNodeResultFailureStateE2ETestCase(
            description="failed virtual task persists failed state row",
            project_name="virtual_failed_task_result_state",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                name = "virtual_failed_task_result_state"
                adapter = "duckdb"
                default_target = "dev"

                [settings]
                virtual_environments = true

                [connection]
                database = "warehouse.duckdb"

                [targets.dev]
                schema = "dev"

                [targets.dev.state]
                backend = "duckdb"
                schema = "sqlbuild_state"

                [targets.dev.state.connection]
                database = "state.duckdb"
                """
                ).strip()
                + "\n",
                "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS id\n",
                "tasks/results.py": (
                    "from sqlbuild.refs import model\n"
                    "from sqlbuild.tasks import task\n\n"
                    "@task(depends_on=model('orders'))\n"
                    "def produce_result(ctx):\n"
                    "    raise RuntimeError('producer failed')\n"
                ),
            },
            command=("--no-color", "build", "--select", "orders"),
            expected_exit_code=1,
            expected_state_rows=(("task", "produce_result", "failed", "producer failed"),),
        ),
        VirtualNodeResultFailureStateE2ETestCase(
            description="failed virtual check persists failed state row",
            project_name="virtual_failed_check_result_state",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                name = "virtual_failed_check_result_state"
                adapter = "duckdb"
                default_target = "dev"

                [settings]
                virtual_environments = true

                [connection]
                database = "warehouse.duckdb"

                [targets.dev]
                schema = "dev"

                [targets.dev.state]
                backend = "duckdb"
                schema = "sqlbuild_state"

                [targets.dev.state.connection]
                database = "state.duckdb"
                """
                ).strip()
                + "\n",
                "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS id\n",
                "tasks/results.py": (
                    "from sqlbuild.refs import model\n"
                    "from sqlbuild.tasks import task\n\n"
                    "@task(depends_on=model('orders'))\n"
                    "def produce_result(ctx):\n"
                    "    return ctx.result(payload={'value': 1})\n"
                ),
                "checks/results.py": (
                    "from sqlbuild.checks import check\n"
                    "from tasks.results import produce_result\n\n"
                    "@check(depends_on=produce_result)\n"
                    "def check_produce_result(ctx):\n"
                    "    return False\n"
                ),
            },
            command=("--no-color", "build", "--select", "orders"),
            expected_exit_code=1,
            expected_state_rows=(
                ("check", "check_produce_result", "failed", ""),
                ("task", "produce_result", "success", ""),
            ),
        ),
        VirtualNodeResultFailureStateE2ETestCase(
            description="skipped virtual task persists skipped state row",
            project_name="virtual_skipped_task_result_state",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                name = "virtual_skipped_task_result_state"
                adapter = "duckdb"
                default_target = "dev"

                [settings]
                virtual_environments = true

                [connection]
                database = "warehouse.duckdb"

                [targets.dev]
                schema = "dev"

                [targets.dev.state]
                backend = "duckdb"
                schema = "sqlbuild_state"

                [targets.dev.state.connection]
                database = "state.duckdb"
                """
                ).strip()
                + "\n",
                "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS id\n",
                "tasks/results.py": (
                    "from sqlbuild.compiler.python_nodes.types import SkipMode\n"
                    "from sqlbuild.refs import model\n"
                    "from sqlbuild.tasks import task\n\n"
                    "@task(depends_on=model('orders'))\n"
                    "def prepare_orders(ctx):\n"
                    "    return ctx.skip('not needed', mode=SkipMode.SOFT)\n"
                ),
            },
            command=("--no-color", "build", "--select", "orders"),
            expected_exit_code=0,
            expected_state_rows=(("task", "prepare_orders", "skipped", "not needed"),),
        ),
        VirtualNodeResultFailureStateE2ETestCase(
            description="skipped virtual loader persists skipped state row",
            project_name="virtual_skipped_loader_result_state",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                name = "virtual_skipped_loader_result_state"
                adapter = "duckdb"
                default_target = "dev"

                [settings]
                virtual_environments = true

                [connection]
                database = "warehouse.duckdb"

                [targets.dev]
                schema = "dev"
                defer_sources_to = "dev"

                [targets.dev.state]
                backend = "duckdb"
                schema = "sqlbuild_state"

                [targets.dev.state.connection]
                database = "state.duckdb"
                """
                ).strip()
                + "\n",
                "tasks/prepare.py": (
                    "from sqlbuild.compiler.python_nodes.types import SkipMode\n"
                    "from sqlbuild.tasks import task\n\n"
                    "@task\n"
                    "def prepare_events(ctx):\n"
                    "    return ctx.skip('no input', mode=SkipMode.HARD)\n"
                ),
                "loaders/events.py": (
                    "from tasks.prepare import prepare_events\n"
                    "from sqlbuild.loaders import loader\n\n"
                    "@loader(depends_on=(prepare_events,))\n"
                    "def raw_events(ctx):\n"
                    "    return [{'event_id': 1}]\n"
                ),
                "sources/raw.yml": (
                    "sources:\n"
                    "  - name: raw_events\n"
                    "    managed: true\n"
                    "    write_strategy: table\n"
                    "    columns:\n"
                    "      - name: event_id\n"
                    "        type: INTEGER\n"
                ),
                "models/events.sql": (
                    'MODEL (materialized table);\n\nSELECT * FROM __source("raw_events")\n'
                ),
            },
            command=("--no-color", "build", "--select", "+events"),
            expected_exit_code=0,
            expected_state_rows=(
                ("loader", "raw_events", "skipped", "Upstream node hard-skipped: prepare_events"),
                ("task", "prepare_events", "skipped", "no input"),
            ),
        ),
        VirtualNodeResultFailureStateE2ETestCase(
            description="non JSON virtual payload persists failed state row",
            project_name="virtual_non_json_payload_result_state",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                name = "virtual_non_json_payload_result_state"
                adapter = "duckdb"
                default_target = "dev"

                [settings]
                virtual_environments = true

                [connection]
                database = "warehouse.duckdb"

                [targets.dev]
                schema = "dev"

                [targets.dev.state]
                backend = "duckdb"
                schema = "sqlbuild_state"

                [targets.dev.state.connection]
                database = "state.duckdb"
                """
                ).strip()
                + "\n",
                "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS id\n",
                "tasks/results.py": (
                    "from sqlbuild.refs import model\n"
                    "from sqlbuild.tasks import task\n\n"
                    "@task(depends_on=model('orders'))\n"
                    "def produce_result(ctx):\n"
                    "    return ctx.result(payload={'bad': {1, 2}})\n"
                ),
            },
            command=("--no-color", "build", "--select", "orders"),
            expected_exit_code=1,
            expected_state_rows=(("task", "produce_result", "failed", "non-JSON-serializable"),),
        ),
        VirtualNodeResultFailureStateE2ETestCase(
            description="non JSON virtual metadata persists failed state row",
            project_name="virtual_non_json_metadata_result_state",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                name = "virtual_non_json_metadata_result_state"
                adapter = "duckdb"
                default_target = "dev"

                [settings]
                virtual_environments = true

                [connection]
                database = "warehouse.duckdb"

                [targets.dev]
                schema = "dev"

                [targets.dev.state]
                backend = "duckdb"
                schema = "sqlbuild_state"

                [targets.dev.state.connection]
                database = "state.duckdb"
                """
                ).strip()
                + "\n",
                "models/orders.sql": "MODEL (materialized table);\n\nSELECT 1 AS id\n",
                "tasks/results.py": (
                    "from sqlbuild.refs import model\n"
                    "from sqlbuild.tasks import task\n\n"
                    "@task(depends_on=model('orders'))\n"
                    "def produce_result(ctx):\n"
                    "    return ctx.result(payload={'ok': True}, metadata={'bad': {1, 2}})\n"
                ),
            },
            command=("--no-color", "build", "--select", "orders"),
            expected_exit_code=1,
            expected_state_rows=(("task", "produce_result", "failed", "non-JSON-serializable"),),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_virtual_node_result_failure_when_building_then_persists_failed_state_row(
    test_case: VirtualNodeResultFailureStateE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files=test_case.repo_files,
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert build_result.returncode == test_case.expected_exit_code, (
        build_result.stdout + build_result.stderr
    )
    state_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_type, node_name, status, error_message "
            "FROM sqlbuild_state.node_results ORDER BY node_type, node_name"
        ),
    )
    assert len(state_rows) == len(test_case.expected_state_rows)
    actual_row: tuple[object, ...]
    expected_row: tuple[object, ...]
    for actual_row, expected_row in zip(state_rows, test_case.expected_state_rows, strict=True):
        assert actual_row[:3] == expected_row[:3]
        assert str(expected_row[3]) in str(actual_row[3] or "")


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPythonIdentityBuildE2ETestCase(
            description="stores Python identities in virtual state for later planning",
            expected_state_identity_rows=(
                ("loader", "raw_orders"),
                ("task", "prepare_orders"),
                ("task", "profile_fact_orders"),
            ),
            expected_warehouse_fingerprint_table_count=0,
            expected_changed_plan_fragments=(
                "Plan ready (0 selected",
                "Python ingress (1)",
                "prepare_orders",
                "task (changed)",
                "python diff:",
                "source diff:",
            ),
            unexpected_changed_plan_fragments=(
                "First run (",
                "Query changed (",
                "fact_orders          table",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_python_identities_when_replanning_then_reads_virtual_state(
    test_case: VirtualPythonIdentityBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_python_identity_state",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_python_identity_state"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n\n"
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n'
                'defer_sources_to = "dev"\n\n'
                "[targets.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n\n'
                "[targets.dev.state.connection]\n"
                'database = "state.duckdb"\n'
            ),
            "tasks/prepare.py": (
                "from pathlib import Path\n"
                "from sqlbuild.tasks import task\n\n"
                "@task\n"
                "def prepare_orders(ctx):\n"
                "    Path(__file__).parents[1].joinpath('prepared.txt').write_text('7')\n"
                "    return ctx.result(payload={'order_id': 7})\n"
            ),
            "loaders/raw.py": (
                "from pathlib import Path\n"
                "from sqlbuild.loaders import loader\n"
                "from tasks.prepare import prepare_orders\n\n"
                "@loader(depends_on=(prepare_orders,))\n"
                "def raw_orders(ctx):\n"
                "    marker = Path(__file__).parents[1].joinpath('prepared.txt')\n"
                "    return [{'order_id': int(marker.read_text())}]\n"
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
            "tasks/profile.py": (
                "from pathlib import Path\n"
                "from sqlbuild.refs import model\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=model('fact_orders'))\n"
                "def profile_fact_orders(ctx):\n"
                "    relation = ctx.relation(model('fact_orders'))\n"
                "    rows = ctx.query(f'SELECT COUNT(*) FROM {relation}').fetchall()[0][0]\n"
                "    Path(__file__).parents[1].joinpath('profile.txt').write_text(str(rows))\n"
                "    return ctx.result(payload={'rows': rows})\n"
            ),
        },
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr

    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_type, node_name "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE node_type IN ('task', 'loader', 'asset', 'check', 'hook') "
            "ORDER BY node_type, node_name"
        ),
    ) == list(test_case.expected_state_identity_rows)
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = '_sqlbuild_fingerprints'"
        ),
    ) == [(test_case.expected_warehouse_fingerprint_table_count,)]

    (project_dir / "tasks" / "prepare.py").write_text(
        "from pathlib import Path\n"
        "from sqlbuild.tasks import task\n\n"
        "@task\n"
        "def prepare_orders(ctx):\n"
        "    Path(__file__).parents[1].joinpath('prepared.txt').write_text('8')\n"
        "    return ctx.result(payload={'order_id': 8})\n",
        encoding="utf-8",
    )
    changed_plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--select", "+fact_orders"),
        project_dir=project_dir,
    )
    assert changed_plan_result.returncode == 0, (
        changed_plan_result.stdout + changed_plan_result.stderr
    )
    for fragment in test_case.expected_changed_plan_fragments:
        assert fragment in changed_plan_result.stdout
    for fragment in test_case.unexpected_changed_plan_fragments:
        assert fragment not in changed_plan_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPythonBuildE2ETestCase(
            description="prints read-side Python failure rows",
            project_name="virtual_python_read_side_failure",
            plan_command=(),
            build_command=("--no-color", "build", "--select", "+fact_orders"),
            expected_build_exit_code=1,
            expected_build_fragments=(
                "python    task      profile_fact_orders",
                "FAIL",
                "profile failed intentionally",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_read_side_python_failure_when_building_then_prints_python_failure_row(
    test_case: VirtualPythonBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_python_read_side_failure"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n\n"
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n\n'
                "[targets.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n\n'
                "[targets.dev.state.connection]\n"
                'database = "state.duckdb"\n'
            ),
            "models/fact_orders.sql": "MODEL (materialized table);\n\nSELECT 7 AS order_id\n",
            "tasks/profile.py": (
                "from sqlbuild.refs import model\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=model('fact_orders'))\n"
                "def profile_fact_orders(ctx):\n"
                "    raise RuntimeError('profile failed intentionally')\n"
            ),
        },
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.build_command,
        project_dir=project_dir,
    )

    assert build_result.returncode == test_case.expected_build_exit_code
    for fragment in test_case.expected_build_fragments:
        assert fragment in build_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPythonBuildE2ETestCase(
            description="prints read-side Python skip rows",
            project_name="virtual_python_read_side_skip",
            plan_command=(),
            build_command=("--no-color", "build", "--select", "+fact_orders"),
            expected_build_exit_code=0,
            expected_build_fragments=(
                "python    task      skip_fact_orders",
                "SKIP",
                "profile not needed",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_read_side_python_skip_when_building_then_prints_python_skip_row(
    test_case: VirtualPythonBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_python_read_side_skip"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n\n"
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n\n'
                "[targets.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n\n'
                "[targets.dev.state.connection]\n"
                'database = "state.duckdb"\n'
            ),
            "models/fact_orders.sql": "MODEL (materialized table);\n\nSELECT 7 AS order_id\n",
            "tasks/profile.py": (
                "from sqlbuild.refs import model\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=model('fact_orders'))\n"
                "def skip_fact_orders(ctx):\n"
                "    return ctx.skip('profile not needed')\n"
            ),
        },
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.build_command,
        project_dir=project_dir,
    )

    assert build_result.returncode == test_case.expected_build_exit_code
    for fragment in test_case.expected_build_fragments:
        assert fragment in build_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPythonBuildE2ETestCase(
            description="no-python only runs loader-side Python nodes",
            project_name="virtual_no_python_nodes_build",
            plan_command=("--no-color", "plan", "--select", "+fact_orders", "--no-python"),
            build_command=("--no-color", "build", "--select", "+fact_orders", "--no-python"),
            expected_build_exit_code=0,
            expected_plan_fragments=("Python ingress (1)", "prepare_orders"),
            expected_absent_plan_fragments=("Python read-side", "profile_fact_orders"),
            expected_prepared_text="7",
            expected_profile_exists=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_python_nodes_when_no_python_then_only_loader_side_python_runs(
    test_case: VirtualPythonBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_no_python_nodes_build"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[settings]\n"
                "virtual_environments = true\n\n"
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n'
                'defer_sources_to = "dev"\n\n'
                "[targets.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n\n'
                "[targets.dev.state.connection]\n"
                'database = "state.duckdb"\n'
            ),
            "tasks/prepare.py": (
                "from pathlib import Path\n"
                "from sqlbuild.tasks import task\n\n"
                "@task\n"
                "def prepare_orders(ctx):\n"
                "    Path(__file__).parents[1].joinpath('prepared.txt').write_text('7')\n"
                "    return ctx.result(payload={'order_id': 7})\n"
            ),
            "loaders/raw.py": (
                "from pathlib import Path\n"
                "from sqlbuild.loaders import loader\n"
                "from tasks.prepare import prepare_orders\n\n"
                "@loader(depends_on=(prepare_orders,))\n"
                "def raw_orders(ctx):\n"
                "    marker = Path(__file__).parents[1].joinpath('prepared.txt')\n"
                "    return [{'order_id': int(marker.read_text())}]\n"
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
            "tasks/profile.py": (
                "from pathlib import Path\n"
                "from sqlbuild.refs import model\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=model('fact_orders'))\n"
                "def profile_fact_orders(ctx):\n"
                "    Path(__file__).parents[1].joinpath('profile.txt').write_text('ran')\n"
                "    return ctx.result()\n"
            ),
        },
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.plan_command,
        project_dir=project_dir,
    )
    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    for fragment in test_case.expected_plan_fragments:
        assert fragment in plan_result.stdout
    for fragment in test_case.expected_absent_plan_fragments:
        assert fragment not in plan_result.stdout

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.build_command,
        project_dir=project_dir,
    )

    assert build_result.returncode == test_case.expected_build_exit_code, (
        build_result.stdout + build_result.stderr
    )
    assert (project_dir / "prepared.txt").read_text(encoding="utf-8") == (
        test_case.expected_prepared_text
    )
    assert (project_dir / "profile.txt").exists() is test_case.expected_profile_exists


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualBuildE2ETestCase(
            description="delete-insert incremental seeds new physical version from prior version",
            expected_build_fragments=(),
            expected_plan_fragments=(),
            expected_query_results=(
                (
                    "SELECT id, amount_cents FROM dev__dev.orders ORDER BY id",
                    ((1, 10), (2, 21), (3, 31)),
                ),
            ),
            expected_ref_rows=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_incremental_change_when_building_then_it_seeds_new_physical_version(
    test_case: VirtualBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_virtual_seeded_incremental_project(
        tmp_path=tmp_path,
        project_name="virtual_seeded_delete_insert",
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
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="INSERT INTO raw.raw_orders VALUES (3, '2026-01-03 00:00:00', 30)",
    )

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "build",
            "--start-cursor-ts",
            "2026-01-02T00:00:00",
            "--end-cursor-ts",
            "2026-01-04T00:00:00",
        ),
        project_dir=project_dir,
    )

    assert build_result.returncode == 0, build_result.stderr
    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )
    ancestry_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT parent_model_name, seed_strategy "
            "FROM sqlbuild_state.physical_relation_ancestry "
            "WHERE model_name = 'orders'"
        ),
    )
    assert ancestry_rows == [("orders", "copy")]


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualBuildE2ETestCase(
            description="explicit cursor overrides work without target or upstream snapshots",
            expected_build_fragments=(),
            expected_plan_fragments=(),
            expected_query_results=(
                (
                    "SELECT id, amount_cents FROM dev__dev.orders ORDER BY id",
                    ((1, 10), (2, 21), (3, 31)),
                ),
            ),
            expected_ref_rows=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_incremental_without_cursor_snapshot_when_building_then_cli_bounds_apply(
    test_case: VirtualBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_virtual_cursor_override_without_snapshot_project(
        tmp_path=tmp_path,
        project_name="virtual_cursor_override_without_snapshot",
    )
    initialize_virtual_seeded_project(project_dir=project_dir)

    rewrite_cursor_override_without_snapshot_model(
        project_dir=project_dir,
        amount_expression="amount_cents + 1",
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "DELETE FROM raw.raw_orders WHERE id = 1; "
            "INSERT INTO raw.raw_orders VALUES (3, '2026-01-03 00:00:00', 30)"
        ),
    )

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "build",
            "--start-cursor-ts",
            "2026-01-02T00:00:00",
            "--end-cursor-ts",
            "2026-01-04T00:00:00",
        ),
        project_dir=project_dir,
    )

    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualCustomMaterializationE2ETestCase(
            description="custom materialization prepare_version seeds changed physical target",
            expected_query_results=(
                (
                    "SELECT id, amount_cents, version_marker FROM dev__dev.orders ORDER BY id",
                    (
                        (1, 10, "prepared"),
                        (2, 21, "materialized"),
                        (3, 30, "materialized"),
                    ),
                ),
            ),
            expected_ancestry_rows=(("custom_prepare_version",),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_custom_materialization_when_model_changes_then_prepare_version_seeds_target(
    test_case: VirtualCustomMaterializationE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_custom_materialization",
        repo_files={
            "sqlbuild_project.toml": build_virtual_plan_project_toml(),
            "materializations/merge_by_id.py": """
from sqlbuild.executor.custom.models import (
    MaterializationContext,
    MaterializationResult,
    PrepareVersionContext,
)


def prepare_version(ctx: PrepareVersionContext) -> None:
    ctx.execute_sql(
        f"CREATE TABLE {ctx.destination} AS "
        f"SELECT id, amount_cents, 'prepared' AS version_marker FROM {ctx.origin_relation}"
    )


def materialize(ctx: MaterializationContext) -> MaterializationResult:
    incoming = (
        "SELECT id, amount_cents, 'materialized' AS version_marker "
        f"FROM ({ctx.sql}) AS model_sql"
    )
    exists = ctx.adapter.relation_exists(
        connection=ctx.connection,
        database=ctx.destination_database,
        schema=ctx.destination_schema,
        name=ctx.destination_name,
    )
    if not exists:
        ctx.execute_sql(f"CREATE TABLE {ctx.destination} AS {incoming}")
    else:
        ctx.execute_sql(
            f"DELETE FROM {ctx.destination} WHERE id IN "
            f"(SELECT id FROM ({ctx.sql}) AS model_sql)"
        )
        ctx.execute_sql(f"INSERT INTO {ctx.destination} {incoming}")
    return MaterializationResult(relation=ctx.destination)
""",
            "models/orders.sql": """
MODEL (materialized merge_by_id);

SELECT 1 AS id, 10 AS amount_cents
UNION ALL SELECT 2 AS id, 20 AS amount_cents
""",
        },
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    first_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert first_build_result.returncode == 0, first_build_result.stderr

    (project_dir / "models" / "orders.sql").write_text(
        """
MODEL (materialized merge_by_id);

SELECT 2 AS id, 21 AS amount_cents
UNION ALL SELECT 3 AS id, 30 AS amount_cents
""",
        encoding="utf-8",
    )

    second_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )

    assert second_build_result.returncode == 0, second_build_result.stderr
    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(
            db_path=project_dir / "warehouse.duckdb",
            sql=query_sql,
        ) == list(expected_rows)
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT seed_strategy FROM sqlbuild_state.physical_relation_ancestry "
            "WHERE model_name = 'orders'"
        ),
    ) == list(test_case.expected_ancestry_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualWaffleShopE2ETestCase(
            description="full waffle shop fixture builds in virtual mode",
            expected_view_names=(
                "customer_status_snapshot",
                "daily_activity_rollup",
                "daily_order_partitioned",
                "daily_revenue",
                "dim_customers",
                "fact_orders",
                "hourly_activity_with_daily_context",
                "hourly_order_activity",
                "order_status_index",
                "stg_customers",
                "stg_orders",
                "stg_payments",
            ),
            expected_function_names=(
                "customer_orders",
                "is_completed_order",
                "is_completed_order_py",
            ),
            expected_query_results=(
                (
                    "SELECT order_id, customer_id, waffle_name, order_status "
                    "FROM dev__dev.fact_orders ORDER BY order_id LIMIT 3",
                    (
                        (1, 1, "Classic Belgian", "completed"),
                        (2, 1, "Cheddar Herb", "completed"),
                        (3, 2, "Chicken and Waffle", "completed"),
                    ),
                ),
                (
                    "SELECT order_id, is_completed_order_py FROM dev__dev.fact_orders "
                    "WHERE order_id IN (1, 10) ORDER BY order_id",
                    ((1, True), (10, False)),
                ),
                (
                    "SELECT order_id, waffle_name, line_total_cents, order_status, "
                    "is_completed_order FROM dev__dev.customer_orders(1) ORDER BY order_id",
                    (
                        (1, "Classic Belgian", 1700, "completed", True),
                        (2, "Cheddar Herb", 1050, "completed", True),
                        (8, "Liege", 950, "completed", True),
                    ),
                ),
                (
                    "SELECT CAST(order_date AS VARCHAR), order_count, waffles_ordered, "
                    "unique_customers FROM dev__dev.daily_order_partitioned ORDER BY order_date",
                    (
                        ("2026-04-01", 3, 6, 2),
                        ("2026-04-02", 3, 3, 2),
                        ("2026-04-03", 2, 3, 2),
                        ("2026-04-04", 2, 6, 2),
                    ),
                ),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_waffle_shop_project_when_virtual_building_then_vde_outputs_are_queryable(
    test_case: VirtualWaffleShopE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)
    (project_dir / "sqlbuild_project.toml").write_text(
        """
name = "waffle_shop"
adapter = "duckdb"
default_target = "dev"

[settings]
virtual_environments = true
default_audit_severity = "warn"

[connection]
database = "waffle_shop.duckdb"

[defaults]
materialized = "table"

[path_defaults.staging]
materialized = "view"

[targets.dev]
schema = "dev"
defer_sources_to = "dev"

[targets.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"

[targets.dev.state.connection]
database = "state.duckdb"
""".lstrip(),
        encoding="utf-8",
    )
    db_path: Path = project_dir / "waffle_shop.duckdb"
    execution_json_path: Path = project_dir / "target" / "virtual-build.json"

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--json-output", str(execution_json_path)),
        project_dir=project_dir,
    )

    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    view_name: str
    for view_name in test_case.expected_view_names:
        assert table_exists(db_path=db_path, schema="dev__dev", table_name=view_name)

    payload: dict[str, object] = json.loads(execution_json_path.read_text(encoding="utf-8"))
    assets: list[dict[str, object]] = list(payload["assets"])  # type: ignore[arg-type]
    function_assets: dict[str, dict[str, object]] = {
        str(asset["name"]): asset for asset in assets if asset.get("kind") in {"udf", "table_fn"}
    }
    function_name: str
    for function_name in test_case.expected_function_names:
        assert function_assets[function_name]["status"] == "success"

    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=db_path, sql=query_sql) == list(expected_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualBuildE2ETestCase(
            description="append bounded incremental seeds only rows before replay window",
            expected_build_fragments=(),
            expected_plan_fragments=(),
            expected_query_results=(
                (
                    "SELECT id, amount_cents FROM dev__dev.orders ORDER BY id",
                    ((1, 10), (2, 21), (3, 31)),
                ),
            ),
            expected_ref_rows=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_append_bounded_change_when_building_then_seed_excludes_replay_window(
    test_case: VirtualBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_virtual_seeded_incremental_project(
        tmp_path=tmp_path,
        project_name="virtual_seeded_append",
        incremental_strategy="append",
        replay_on_change="bounded-7d",
    )
    initialize_virtual_seeded_project(project_dir=project_dir)

    rewrite_incremental_orders_model(
        project_dir=project_dir,
        incremental_strategy="append",
        replay_on_change="bounded-7d",
        amount_expression="amount_cents + 1",
    )
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="INSERT INTO raw.raw_orders VALUES (3, '2026-01-03 00:00:00', 30)",
    )

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "build",
            "--start-cursor-ts",
            "2026-01-02T00:00:00",
            "--end-cursor-ts",
            "2026-01-04T00:00:00",
        ),
        project_dir=project_dir,
    )

    assert build_result.returncode == 0, build_result.stderr
    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )
    ancestry_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT parent_model_name, seed_strategy "
            "FROM sqlbuild_state.physical_relation_ancestry "
            "WHERE model_name = 'orders'"
        ),
    )
    assert ancestry_rows == [("orders", "bounded_append_copy")]


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualBuildE2ETestCase(
            description="explicit VDE graph selection diverges refs and leaves downstream working",
            expected_build_fragments=("name: kevin",),
            expected_plan_fragments=(
                "status: working",
                "stale roots: 0",
                "stale model set: orders_rollup",
            ),
            expected_query_results=(
                ("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((1,),)),
                ("SELECT id FROM dev__kevin.fact_orders ORDER BY id", ((2,),)),
                ("SELECT order_count FROM dev__kevin.orders_rollup", ((1,),)),
            ),
            expected_ref_rows=(("fact_orders",), ("stg_orders",)),
            expected_default_plan_fragments=(
                "query diff:",
                "-SELECT 1 AS id",
                "+SELECT 2 AS id",
            ),
            expected_final_plan_fragments=("Plan ready (0 selected)", "status: finalized"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_explicit_virtual_env_with_graph_selection_when_building_then_refs_diverge(
    test_case: VirtualBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_build_explicit_vde",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id")
        | {
            "models/orders_rollup.sql": (
                'MODEL ();\n\nSELECT COUNT(*) AS order_count FROM __ref("fact_orders")\n'
            )
        },
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    default_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert default_build_result.returncode == 0, default_build_result.stderr

    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )

    default_plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan"),
        project_dir=project_dir,
    )
    assert default_plan_result.returncode == 0, default_plan_result.stderr
    for fragment in test_case.expected_default_plan_fragments:
        assert fragment in default_plan_result.stdout

    branch_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "build",
            "--virtual-env",
            "kevin",
            "--select",
            "+fact_orders",
            "--select",
            "dim_customers",
        ),
        project_dir=project_dir,
    )

    assert branch_build_result.returncode == 0, branch_build_result.stderr
    for fragment in test_case.expected_build_fragments:
        assert fragment in branch_build_result.stdout
    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(
            db_path=project_dir / "warehouse.duckdb",
            sql=query_sql,
        ) == list(expected_rows)
    divergent_refs: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT dev.node_name "
            "FROM sqlbuild_state.virtual_environment_node_refs dev "
            "JOIN sqlbuild_state.virtual_environment_node_refs kevin "
            "ON dev.node_name = kevin.node_name "
            "WHERE dev.virtual_environment_name = 'dev' "
            "AND kevin.virtual_environment_name = 'kevin' "
            "AND dev.node_type = 'model' AND kevin.node_type = 'model' "
            "AND dev.version_hash <> kevin.version_hash "
            "ORDER BY dev.node_name"
        ),
    )
    assert divergent_refs == list(test_case.expected_ref_rows)

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--virtual-env", "kevin"),
        project_dir=project_dir,
    )

    assert plan_result.returncode == 0, plan_result.stderr
    for fragment in test_case.expected_plan_fragments:
        assert fragment in plan_result.stdout

    final_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "kevin"),
        project_dir=project_dir,
    )
    assert final_build_result.returncode == 0, final_build_result.stderr

    final_plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--virtual-env", "kevin"),
        project_dir=project_dir,
    )
    assert final_plan_result.returncode == 0, final_plan_result.stderr
    for fragment in test_case.expected_final_plan_fragments:
        assert fragment in final_plan_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualBuildSelectionGuardE2ETestCase(
            description="selected downstream with stale upstream blocks then expands",
            blocked_command=("--no-color", "build", "--select", "fact_orders"),
            expanded_command=(
                "--no-color",
                "build",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
            ),
            expected_blocked_fragments=("missing stale required upstream models: stg_orders",),
            expected_query_results=(("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((2,),)),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_build_selected_downstream_with_stale_upstream_when_running_then_it_blocks(
    test_case: VirtualBuildSelectionGuardE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_build_guard",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    default_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert default_build_result.returncode == 0, default_build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )

    blocked_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.blocked_command,
        project_dir=project_dir,
    )

    assert blocked_result.returncode != 0
    blocked_output: str = blocked_result.stdout + blocked_result.stderr
    fragment: str
    for fragment in test_case.expected_blocked_fragments:
        assert fragment in blocked_output

    expanded_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.expanded_command,
        project_dir=project_dir,
    )

    assert expanded_result.returncode == 0, expanded_result.stderr
    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(
            db_path=project_dir / "warehouse.duckdb",
            sql=query_sql,
        ) == list(expected_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualRollbackE2ETestCase(
            description="rollback blocks when checkpoint physical relation is missing",
            rollback_command=("--no-color", "rollback"),
            expected_exit_code=1,
            expected_rollback_fragments=(),
            expected_stderr_fragments=(
                "error[S024]",
                "checkpoint references missing warehouse relation",
            ),
            expected_query_results=(),
            expected_checkpoint_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_checkpoint_physical_relation_missing_when_rolling_back_then_it_blocks_cleanly(
    test_case: VirtualRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_rollback_missing_physical",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
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
    assert initial_build_result.returncode == 0, initial_build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    changed_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert changed_build_result.returncode == 0, changed_build_result.stderr
    checkpoint_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql="SELECT checkpoint_id FROM sqlbuild_state.virtual_environment_checkpoints",
    )
    assert len(checkpoint_rows) == test_case.expected_checkpoint_count
    initial_physical_relation: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT pr.schema_name, pr.relation_name "
            "FROM sqlbuild_state.virtual_environment_checkpoints cp "
            "JOIN sqlbuild_state.virtual_environment_checkpoint_model_refs cr "
            "ON cp.checkpoint_id = cr.checkpoint_id "
            "JOIN sqlbuild_state.physical_relations pr "
            "ON pr.artifact_type = 'model' AND pr.artifact_name = cr.model_name "
            "AND pr.version_hash = cr.version_hash "
            "WHERE cp.virtual_environment_name = 'dev' AND cr.model_name = 'stg_orders' "
            "ORDER BY cp.created_at ASC LIMIT 1"
        ),
    )
    assert initial_physical_relation
    schema_name, relation_name = initial_physical_relation[0]
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=f'DROP TABLE "{schema_name}"."{relation_name}"',
    )

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.rollback_command,
        project_dir=project_dir,
    )

    assert rollback_result.returncode == test_case.expected_exit_code
    fragment: str
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in rollback_result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualRollbackE2ETestCase(
            description="rollback blocks when no previous checkpoint exists",
            rollback_command=("--no-color", "rollback"),
            expected_exit_code=1,
            expected_rollback_fragments=(),
            expected_stderr_fragments=(
                "error[S021]",
                "no previous finalized checkpoint is available for rollback",
            ),
            expected_query_results=(),
            expected_checkpoint_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_only_current_checkpoint_when_rolling_back_then_it_blocks_cleanly(
    test_case: VirtualRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_rollback_no_previous",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
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
    checkpoint_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql="SELECT checkpoint_id FROM sqlbuild_state.virtual_environment_checkpoints",
    )
    assert len(checkpoint_rows) == test_case.expected_checkpoint_count

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.rollback_command,
        project_dir=project_dir,
    )

    assert rollback_result.returncode == test_case.expected_exit_code
    fragment: str
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in rollback_result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualRollbackE2ETestCase(
            description="rollback blocks when target VDE lock exists",
            rollback_command=("rollback", "--virtual-env", "dev"),
            expected_exit_code=1,
            expected_rollback_fragments=(),
            expected_stderr_fragments=("virtual environment 'dev' is locked",),
            expected_query_results=(),
            expected_checkpoint_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_target_virtual_environment_lock_when_rolling_back_then_it_fails_clearly(
    test_case: VirtualRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_rollback_locked_target",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
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
    assert initial_build_result.returncode == 0, initial_build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    changed_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert changed_build_result.returncode == 0, changed_build_result.stderr
    checkpoint_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql="SELECT checkpoint_id FROM sqlbuild_state.virtual_environment_checkpoints",
    )
    assert len(checkpoint_rows) == test_case.expected_checkpoint_count
    execute_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "INSERT INTO sqlbuild_state.locks "
            "(lock_key, owner_id, expires_at, created_at, updated_at) "
            "VALUES ('virtual_env:dev', 'test-owner', TIMESTAMP '2999-01-01', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
    )

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.rollback_command,
        project_dir=project_dir,
    )

    assert rollback_result.returncode == test_case.expected_exit_code
    fragment: str
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in rollback_result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualRollbackE2ETestCase(
            description="checkpoint show blocks for unknown checkpoint",
            rollback_command=("--no-color", "state", "checkpoints", "show", "missing"),
            expected_exit_code=1,
            expected_rollback_fragments=(),
            expected_stderr_fragments=("error[C905]", "unknown checkpoint 'missing'"),
            expected_query_results=(),
            expected_checkpoint_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unknown_checkpoint_when_showing_checkpoint_then_it_blocks_cleanly(
    test_case: VirtualRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_checkpoint_show_unknown",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
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
    checkpoint_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql="SELECT checkpoint_id FROM sqlbuild_state.virtual_environment_checkpoints",
    )
    assert len(checkpoint_rows) == test_case.expected_checkpoint_count

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.rollback_command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code
    fragment: str
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPromoteE2ETestCase(
            description="whole VDE promotion swaps target refs and views",
            promote_command=("--no-color", "promote", "--from", "pr", "--to", "dev"),
            expected_promote_fragments=(
                "Virtual promotion complete",
                "pr -> dev",
                "target status          finalized",
                "promoted models        3",
                "remaining stale models 0",
            ),
            expected_query_results=(("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((2,),)),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_env_when_promoting_then_it_updates_target_refs_and_views(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_promote_whole",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    default_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert default_build_result.returncode == 0, default_build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    branch_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr"),
        project_dir=project_dir,
    )
    assert branch_build_result.returncode == 0, branch_build_result.stderr

    promote_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )

    assert promote_result.returncode == 0, promote_result.stderr
    fragment: str
    for fragment in test_case.expected_promote_fragments:
        assert fragment in promote_result.stdout
    checkpoint_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT checkpoint_id FROM sqlbuild_state.virtual_environment_checkpoints "
            "WHERE virtual_environment_name = 'dev'"
        ),
    )
    assert len(checkpoint_rows) == 2
    operation_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT operation_type, status, virtual_environment_name "
            "FROM sqlbuild_state.state_operations ORDER BY created_at DESC LIMIT 1"
        ),
    )
    assert operation_rows == [("promote", "succeeded", "dev")]
    operation_event_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT action, status FROM sqlbuild_state.state_operation_events ORDER BY created_at"
        ),
    )
    assert operation_event_rows[-2:] == [("start", "running"), ("finish", "succeeded")]
    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(
            db_path=project_dir / "warehouse.duckdb",
            sql=query_sql,
        ) == list(expected_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPromoteE2ETestCase(
            description="whole VDE promotion carries seed refs and views",
            promote_command=("--no-color", "promote", "--from", "pr", "--to", "dev"),
            expected_promote_fragments=(),
            expected_query_results=(
                (
                    "SELECT id, amount_cents FROM dev__dev.order_amounts ORDER BY id",
                    ((1, 200),),
                ),
                (
                    "SELECT id, amount_cents FROM dev__dev.stg_orders ORDER BY id",
                    ((1, 200),),
                ),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seed_change_when_promoting_then_it_updates_destination_seed_refs_and_views(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_promote_seed_refs",
        repo_files=build_virtual_seed_lifecycle_repo_files(amount_cents=100),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "id,amount_cents\n1,200\n", encoding="utf-8"
    )
    assert (
        run_sqb(
            command=("--no-color", "build", "--virtual-env", "pr"), project_dir=project_dir
        ).returncode
        == 0
    )

    promote_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )

    assert promote_result.returncode == 0, promote_result.stderr
    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )
    seed_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT virtual_environment_name, node_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name IN ('dev', 'pr') AND node_type = 'seed' "
            "ORDER BY virtual_environment_name"
        ),
    )
    assert len(seed_ref_rows) == 2
    assert seed_ref_rows[0][2] == seed_ref_rows[1][2]
    checkpoint_seed_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT seed_name FROM sqlbuild_state.virtual_environment_checkpoint_seed_refs "
            "WHERE seed_name = 'order_amounts'"
        ),
    )
    assert checkpoint_seed_rows


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPromoteE2ETestCase(
            description="partial promotion carries upstream seed refs and views",
            promote_command=(
                "--no-color",
                "promote",
                "--from",
                "pr",
                "--to",
                "dev",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
                "--allow-partial-promotion",
            ),
            expected_promote_fragments=(),
            expected_query_results=(
                (
                    "SELECT id, amount_cents FROM dev__dev.order_amounts ORDER BY id",
                    ((1, 200),),
                ),
                (
                    "SELECT id, multiplier FROM dev__dev.amount_multipliers ORDER BY id",
                    ((1, 2),),
                ),
                ("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((1,),)),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seed_change_when_partially_promoting_then_it_updates_upstream_seed_refs_and_views(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_promote_partial_seed_refs",
        repo_files=build_virtual_multi_seed_lifecycle_repo_files(amount_cents=100, multiplier=1),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "id,amount_cents\n1,200\n", encoding="utf-8"
    )
    (project_dir / "seeds" / "amount_multipliers.csv").write_text(
        "id,multiplier\n1,2\n", encoding="utf-8"
    )
    assert (
        run_sqb(
            command=("--no-color", "build", "--virtual-env", "pr"), project_dir=project_dir
        ).returncode
        == 0
    )

    promote_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )

    assert promote_result.returncode == 0, promote_result.stdout + promote_result.stderr
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )
    seed_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT virtual_environment_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name IN ('dev', 'pr') "
            "AND node_type = 'seed' "
            "AND node_name IN ('order_amounts', 'amount_multipliers') "
            "ORDER BY node_name, virtual_environment_name"
        ),
    )
    assert len(seed_ref_rows) == 4
    assert seed_ref_rows[0][1] == seed_ref_rows[1][1]
    assert seed_ref_rows[2][1] == seed_ref_rows[3][1]


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPromoteE2ETestCase(
            description="whole VDE promotion carries function definitions",
            promote_command=("--no-color", "promote", "--from", "pr", "--to", "dev"),
            expected_promote_fragments=(
                "Virtual promotion complete",
                "pr -> dev",
                "target status          finalized",
            ),
            expected_query_results=(
                ("SELECT is_large FROM dev__dev.fact_orders ORDER BY is_large", ((True,),)),
                ("SELECT dev__dev.is_large_order(7)", ((True,),)),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_function_change_when_promoting_then_it_publishes_target_function_definition(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_promote_function_definition",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 7 AS id")
        | {
            "models/fact_orders.sql": (
                "MODEL (materialized view);\n\n"
                'SELECT __udf("is_large_order")(id) AS is_large FROM __ref("stg_orders")\n'
            ),
            "functions/sql/is_large_order.sql": (
                "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, "
                "replay_on_change full);\n\n"
                "amount > 9\n"
            ),
        },
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT dev__dev.is_large_order(7)",
    ) == [(False,)]

    (project_dir / "functions" / "sql" / "is_large_order.sql").write_text(
        "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, replay_on_change full);\n\n"
        "amount > 5\n",
        encoding="utf-8",
    )
    assert (
        run_sqb(
            command=("--no-color", "build", "--virtual-env", "pr"), project_dir=project_dir
        ).returncode
        == 0
    )
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT is_large FROM dev__pr.fact_orders ORDER BY is_large",
    ) == [(True,)]
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT is_large FROM dev__dev.fact_orders ORDER BY is_large",
    ) == [(False,)]

    promote_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )

    assert promote_result.returncode == 0, promote_result.stderr
    for fragment in test_case.expected_promote_fragments:
        assert fragment in promote_result.stdout
    function_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type IN ('udf', 'table_fn')"
        ),
    )
    assert len(function_ref_rows) == 1
    for sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=sql) == list(
            expected_rows
        )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualRollbackE2ETestCase(
            description="whole VDE rollback restores previous finalized checkpoint",
            rollback_command=("--no-color", "rollback"),
            expected_rollback_fragments=(
                "Virtual rollback complete",
                "virtual environment  dev",
                "status               finalized",
                "rolled back models   2",
                "rolled back model set",
            ),
            expected_query_results=(("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((1,),)),),
            expected_checkpoint_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_finalized_checkpoints_when_rolling_back_then_it_restores_previous_refs_and_views(
    test_case: VirtualRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_rollback_whole",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
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
    assert initial_build_result.returncode == 0, initial_build_result.stderr
    initial_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'model' "
            "ORDER BY node_name"
        ),
    )
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    changed_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert changed_build_result.returncode == 0, changed_build_result.stderr
    checkpoint_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql="SELECT checkpoint_id FROM sqlbuild_state.virtual_environment_checkpoints",
    )
    assert len(checkpoint_rows) == test_case.expected_checkpoint_count
    checkpoint_id: str = str(checkpoint_rows[0][0])
    list_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "checkpoints", "list"),
        project_dir=project_dir,
    )
    assert list_result.returncode == 0, list_result.stderr
    assert "Virtual environment checkpoints" in list_result.stdout
    assert "dev" in list_result.stdout
    assert checkpoint_id in list_result.stdout
    show_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "checkpoints", "show", checkpoint_id),
        project_dir=project_dir,
    )
    assert show_result.returncode == 0, show_result.stderr
    assert "Virtual environment checkpoint" in show_result.stdout
    assert checkpoint_id in show_result.stdout
    assert "stg_orders" in show_result.stdout
    diff_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "checkpoints", "diff", checkpoint_id),
        project_dir=project_dir,
    )
    assert diff_result.returncode == 0, diff_result.stderr
    assert "Virtual environment checkpoint diff" in diff_result.stdout
    assert "changed refs     2" in diff_result.stdout
    assert "stg_orders" in diff_result.stdout

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.rollback_command,
        project_dir=project_dir,
    )

    assert rollback_result.returncode == 0, rollback_result.stderr
    fragment: str
    for fragment in test_case.expected_rollback_fragments:
        assert fragment in rollback_result.stdout
    rolled_back_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'model' "
            "ORDER BY node_name"
        ),
    )
    assert rolled_back_ref_rows == initial_ref_rows
    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(
            db_path=project_dir / "warehouse.duckdb",
            sql=query_sql,
        ) == list(expected_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualRollbackE2ETestCase(
            description="whole rollback restores seed refs and views",
            rollback_command=("--no-color", "rollback"),
            expected_rollback_fragments=(),
            expected_query_results=(
                (
                    "SELECT id, amount_cents FROM dev__dev.order_amounts ORDER BY id",
                    ((1, 100),),
                ),
                (
                    "SELECT id, multiplier FROM dev__dev.amount_multipliers ORDER BY id",
                    ((1, 1),),
                ),
                (
                    "SELECT id, amount_cents FROM dev__dev.stg_orders ORDER BY id",
                    ((1, 100),),
                ),
            ),
            expected_checkpoint_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seed_change_when_rolling_back_then_it_restores_checkpointed_seed_refs_and_views(
    test_case: VirtualRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_rollback_seed_refs",
        repo_files=build_virtual_multi_seed_lifecycle_repo_files(amount_cents=100, multiplier=1),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    initial_seed_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'seed' "
            "ORDER BY node_name"
        ),
    )
    checkpoint_id: str = str(
        query_duckdb(
            db_path=project_dir / "state.duckdb",
            sql=(
                "SELECT checkpoint_id FROM sqlbuild_state.virtual_environment_checkpoints "
                "WHERE virtual_environment_name = 'dev' ORDER BY created_at LIMIT 1"
            ),
        )[0][0]
    )
    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "id,amount_cents\n1,200\n", encoding="utf-8"
    )
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT id, amount_cents FROM dev__dev.order_amounts ORDER BY id",
    ) == [(1, 200)]
    show_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "checkpoints", "show", checkpoint_id),
        project_dir=project_dir,
    )
    assert show_result.returncode == 0, show_result.stderr
    assert "Seed refs" in show_result.stdout
    assert "order_amounts" in show_result.stdout
    diff_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "state", "checkpoints", "diff", checkpoint_id),
        project_dir=project_dir,
    )
    assert diff_result.returncode == 0, diff_result.stderr
    assert "changed seeds    1" in diff_result.stdout

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.rollback_command,
        project_dir=project_dir,
    )

    assert rollback_result.returncode == 0, rollback_result.stderr
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )
    rolled_back_seed_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'seed' "
            "ORDER BY node_name"
        ),
    )
    assert rolled_back_seed_ref_rows == initial_seed_ref_rows


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualRollbackE2ETestCase(
            description="partial rollback restores upstream seed refs and views",
            rollback_command=(
                "--no-color",
                "rollback",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
                "--allow-partial-rollback",
            ),
            expected_rollback_fragments=(),
            expected_query_results=(
                (
                    "SELECT id, amount_cents FROM dev__dev.order_amounts ORDER BY id",
                    ((1, 100),),
                ),
            ),
            expected_checkpoint_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seed_change_when_partial_rollback_then_restores_upstream_seed_refs_and_views(
    test_case: VirtualRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_rollback_partial_seed_refs",
        repo_files=build_virtual_multi_seed_lifecycle_repo_files(amount_cents=100, multiplier=1),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    initial_seed_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'seed' "
            "ORDER BY node_name"
        ),
    )
    (project_dir / "seeds" / "order_amounts.csv").write_text(
        "id,amount_cents\n1,200\n", encoding="utf-8"
    )
    (project_dir / "seeds" / "amount_multipliers.csv").write_text(
        "id,multiplier\n1,2\n", encoding="utf-8"
    )
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.rollback_command,
        project_dir=project_dir,
    )

    assert rollback_result.returncode == 0, rollback_result.stdout + rollback_result.stderr
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )
    rolled_back_seed_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT node_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE virtual_environment_name = 'dev' AND node_type = 'seed' "
            "ORDER BY node_name"
        ),
    )
    assert rolled_back_seed_ref_rows == initial_seed_ref_rows


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualRollbackE2ETestCase(
            description="whole VDE rollback restores checkpointed function definitions",
            rollback_command=("--no-color", "rollback"),
            expected_rollback_fragments=(
                "Virtual rollback complete",
                "status               finalized",
            ),
            expected_query_results=(
                ("SELECT is_large FROM dev__dev.fact_orders ORDER BY is_large", ((False,),)),
            ),
            expected_checkpoint_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_function_change_when_rolling_back_then_it_restores_checkpointed_definition(
    test_case: VirtualRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_rollback_function_definition",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 7 AS id")
        | {
            "models/fact_orders.sql": (
                "MODEL (materialized view);\n\n"
                'SELECT __udf("is_large_order")(id) AS is_large FROM __ref("stg_orders")\n'
            ),
            "functions/sql/is_large_order.sql": (
                "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, "
                "replay_on_change full);\n\n"
                "amount > 9\n"
            ),
        },
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT is_large FROM dev__dev.fact_orders ORDER BY is_large",
    ) == [(False,)]

    (project_dir / "functions" / "sql" / "is_large_order.sql").write_text(
        "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, replay_on_change full);\n\n"
        "amount > 5\n",
        encoding="utf-8",
    )
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    assert query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql="SELECT is_large FROM dev__dev.fact_orders ORDER BY is_large",
    ) == [(True,)]
    checkpoint_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql="SELECT COUNT(*) FROM sqlbuild_state.virtual_environment_checkpoints",
    )
    checkpoint_function_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql="SELECT COUNT(*) FROM sqlbuild_state.virtual_environment_checkpoint_function_refs",
    )

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.rollback_command,
        project_dir=project_dir,
    )

    assert int(checkpoint_rows[0][0]) == test_case.expected_checkpoint_count
    assert int(checkpoint_function_ref_rows[0][0]) == 2
    assert rollback_result.returncode == 0, rollback_result.stderr
    for fragment in test_case.expected_rollback_fragments:
        assert fragment in rollback_result.stdout
    for sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=sql) == list(
            expected_rows
        )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualExplicitCheckpointRollbackE2ETestCase(
            description="explicit checkpoint restores selected checkpoint",
            rollback_command_prefix=("--no-color", "rollback", "--checkpoint-id"),
            expected_query_results=(("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((1,),)),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_explicit_checkpoint_when_rolling_back_then_it_restores_that_checkpoint(
    test_case: VirtualExplicitCheckpointRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_rollback_explicit_checkpoint",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    initial_checkpoint_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT checkpoint_id FROM sqlbuild_state.virtual_environment_checkpoints "
            "ORDER BY created_at ASC, checkpoint_id ASC"
        ),
    )
    initial_checkpoint_id: str = str(initial_checkpoint_rows[0][0])
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 3 AS id\n",
        encoding="utf-8",
    )
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=(*test_case.rollback_command_prefix, initial_checkpoint_id),
        project_dir=project_dir,
    )

    assert rollback_result.returncode == 0, rollback_result.stderr
    assert f"checkpoint           {initial_checkpoint_id}" in rollback_result.stdout
    for sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=sql) == list(
            expected_rows
        )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPartialRollbackE2ETestCase(
            description="partial rollback requires override and marks VDE working",
            blocked_command=("--no-color", "rollback", "--select", "stg_orders"),
            allowed_command=(
                "--no-color",
                "rollback",
                "--select",
                "stg_orders",
                "--allow-partial-rollback",
            ),
            expected_blocked_stderr_fragments=(
                "rollback would leave target virtual environment working",
            ),
            expected_allowed_stdout_fragments=(
                "status               active",
                "rolled back models   1",
            ),
            expected_query_results=(("SELECT id FROM dev__dev.stg_orders ORDER BY id", ((1,),)),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_partial_rollback_when_allowed_then_it_marks_vde_working(
    test_case: VirtualPartialRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_rollback_partial",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0

    blocked_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.blocked_command,
        project_dir=project_dir,
    )
    assert blocked_result.returncode == 1
    for fragment in test_case.expected_blocked_stderr_fragments:
        assert fragment in blocked_result.stderr

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.allowed_command,
        project_dir=project_dir,
    )

    assert rollback_result.returncode == 0, rollback_result.stderr
    for fragment in test_case.expected_allowed_stdout_fragments:
        assert fragment in rollback_result.stdout
    for sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=sql) == list(
            expected_rows
        )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPartialRollbackE2ETestCase(
            description="partial rollback can include stale required upstreams",
            blocked_command=(
                "--no-color",
                "rollback",
                "--select",
                "fact_orders",
                "--allow-partial-rollback",
            ),
            allowed_command=(
                "--no-color",
                "rollback",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
                "--allow-partial-rollback",
            ),
            expected_blocked_stderr_fragments=(
                "selected rollback scope is missing stale required upstream models",
                "stg_orders",
            ),
            expected_allowed_stdout_fragments=(
                "status               finalized",
                "rolled back models   2",
            ),
            expected_query_results=(("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((1,),)),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_partial_rollback_missing_stale_upstreams_when_including_them_then_it_succeeds(
    test_case: VirtualPartialRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_rollback_include_stale_upstreams",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0

    blocked_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.blocked_command,
        project_dir=project_dir,
    )
    assert blocked_result.returncode == 1
    for fragment in test_case.expected_blocked_stderr_fragments:
        assert fragment in blocked_result.stderr

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.allowed_command,
        project_dir=project_dir,
    )

    assert rollback_result.returncode == 0, rollback_result.stderr
    for fragment in test_case.expected_allowed_stdout_fragments:
        assert fragment in rollback_result.stdout
    for sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=sql) == list(
            expected_rows
        )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPartialRollbackE2ETestCase(
            description="partial rollback matches checkpoint when workspace changed",
            blocked_command=(),
            allowed_command=(
                "--no-color",
                "rollback",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
            ),
            expected_blocked_stderr_fragments=(),
            expected_allowed_stdout_fragments=(
                "status               finalized",
                "rolled back models   2",
            ),
            expected_query_results=(("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((1,),)),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_partial_rollback_matches_checkpoint_when_workspace_changed_then_no_override_needed(
    test_case: VirtualPartialRollbackE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_rollback_stale_workspace",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 3 AS id\n",
        encoding="utf-8",
    )

    rollback_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.allowed_command,
        project_dir=project_dir,
    )

    assert rollback_result.returncode == 0, rollback_result.stdout + rollback_result.stderr
    fragment: str
    for fragment in test_case.expected_allowed_stdout_fragments:
        assert fragment in rollback_result.stdout
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPromoteE2ETestCase(
            description="finalized source promotes after workspace changes again",
            promote_command=("--no-color", "promote", "--from", "pr", "--to", "dev"),
            expected_promote_fragments=(
                "Virtual promotion complete",
                "target status          finalized",
            ),
            expected_query_results=(("SELECT id FROM dev__dev.stg_orders ORDER BY id", ((2,),)),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_finalized_source_vde_when_workspace_changes_again_then_whole_promotion_succeeds(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_promote_finalized_stale_workspace",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    default_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert default_build_result.returncode == 0, default_build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    branch_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr"),
        project_dir=project_dir,
    )
    assert branch_build_result.returncode == 0, branch_build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 3 AS id\n",
        encoding="utf-8",
    )

    promote_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )

    assert promote_result.returncode == 0, promote_result.stdout + promote_result.stderr
    for fragment in test_case.expected_promote_fragments:
        assert fragment in promote_result.stdout
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPromoteE2ETestCase(
            description="partial promotion requires explicit working target acceptance",
            blocked_command=(
                "--no-color",
                "promote",
                "--from",
                "pr",
                "--to",
                "dev",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
            ),
            promote_command=(
                "--no-color",
                "promote",
                "--from",
                "pr",
                "--to",
                "dev",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
                "--allow-partial-promotion",
            ),
            expected_blocked_fragments=(
                "promotion would leave target virtual environment working",
                "orders_rollup",
                "--allow-partial-promotion",
            ),
            expected_promote_fragments=(
                "target status          working",
                "promoted models        2",
                "remaining stale set: orders_rollup",
            ),
            expected_query_results=(
                ("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((2,),)),
                ("SELECT order_count FROM dev__dev.orders_rollup", ((1,),)),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_partial_virtual_promotion_when_target_stays_working_then_it_requires_override(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_promote_partial",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id")
        | {
            "models/orders_rollup.sql": (
                'MODEL ();\n\nSELECT COUNT(*) AS order_count FROM __ref("fact_orders")\n'
            )
        },
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    default_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert default_build_result.returncode == 0, default_build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    branch_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr"),
        project_dir=project_dir,
    )
    assert branch_build_result.returncode == 0, branch_build_result.stderr

    blocked_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.blocked_command,
        project_dir=project_dir,
    )
    assert blocked_result.returncode != 0
    blocked_output: str = blocked_result.stdout + blocked_result.stderr
    fragment: str
    for fragment in test_case.expected_blocked_fragments:
        assert fragment in blocked_output

    promote_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )
    assert promote_result.returncode == 0, promote_result.stderr
    for fragment in test_case.expected_promote_fragments:
        assert fragment in promote_result.stdout
    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(
            db_path=project_dir / "warehouse.duckdb",
            sql=query_sql,
        ) == list(expected_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPromoteE2ETestCase(
            description="standard mode promotion fails with mode error",
            promote_command=("promote", "--from", "pr", "--to", "dev"),
            expected_promote_fragments=("promote requires virtual_environments = true",),
            expected_query_results=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_direct_mode_project_when_promoting_then_it_fails_with_mode_error(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_promote_guard",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "direct_promote_guard"\n'
                'adapter = "duckdb"\n'
                'default_target = "dev"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[targets.dev]\n"
                'schema = "dev"\n'
            ),
            "models/stg_orders.sql": "MODEL ();\n\nSELECT 1 AS id\n",
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_promote_fragments:
        assert fragment in result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPromoteE2ETestCase(
            description="missing promoted physical relation fails clearly",
            promote_command=(
                "promote",
                "--from",
                "pr",
                "--to",
                "dev",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
                "--allow-partial-promotion",
            ),
            expected_promote_fragments=("fact_orders",),
            expected_query_results=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_promoted_physical_relation_is_missing_when_promoting_then_it_fails_clearly(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_promote_missing_physical",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    default_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert default_build_result.returncode == 0, default_build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    branch_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr"),
        project_dir=project_dir,
    )
    assert branch_build_result.returncode == 0, branch_build_result.stderr
    physical_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT schema_name, relation_name "
            "FROM sqlbuild_state.physical_relations "
            "WHERE artifact_type = 'model' AND artifact_name = 'fact_orders' "
            "ORDER BY created_at DESC LIMIT 1"
        ),
    )
    assert physical_rows
    schema_name, relation_name = physical_rows[0]
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=f'DROP TABLE "{schema_name}"."{relation_name}"',
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    output: str = result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_promote_fragments:
        assert fragment in output


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPromoteE2ETestCase(
            description="target VDE lock blocks promotion",
            promote_command=("promote", "--from", "pr", "--to", "dev"),
            expected_promote_fragments=("virtual environment 'dev' is locked",),
            expected_query_results=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_target_virtual_environment_lock_when_promoting_then_it_fails_clearly(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_promote_locked_target",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    default_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert default_build_result.returncode == 0, default_build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    branch_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr"),
        project_dir=project_dir,
    )
    assert branch_build_result.returncode == 0, branch_build_result.stderr
    execute_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "INSERT INTO sqlbuild_state.locks "
            "(lock_key, owner_id, expires_at, created_at, updated_at) "
            "VALUES ('virtual_env:dev', 'test-owner', TIMESTAMP '2999-01-01', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    output: str = result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_promote_fragments:
        assert fragment in output


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPromoteE2ETestCase(
            description="interrupted promotion records failed operation",
            promote_command=("promote", "--from", "pr", "--to", "dev"),
            expected_promote_fragments=("simulated promote view refresh failure",),
            expected_query_results=(("SELECT id FROM dev__dev.fact_orders", ((1,),)),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_view_refresh_failure_when_promoting_then_operation_is_marked_failed(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_promote_failed_operation",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id")
        | {
            "adapters/failing_duckdb.py": (
                "from typing import Any\n"
                "from sqlbuild.adapter.classes.statement_recorder import StatementRecorder\n"
                "from sqlbuild.adapter.exceptions import AdapterUserError\n"
                "from sqlbuild.adapters.duckdb.client import DuckDbAdapter\n\n"
                "class FailingDuckDbAdapter(DuckDbAdapter):\n"
                "    adapter_name = 'failing_duckdb'\n\n"
                "    def create_view_as(\n"
                "        self,\n"
                "        connection: Any,\n"
                "        *,\n"
                "        destination: str,\n"
                "        sql: str,\n"
                "        statement_recorder: StatementRecorder,\n"
                "    ) -> None:\n"
                "        raise AdapterUserError('simulated promote view refresh failure')\n"
            )
        },
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    assert (
        run_sqb(
            command=("--no-color", "build", "--virtual-env", "pr"), project_dir=project_dir
        ).returncode
        == 0
    )
    (project_dir / "sqlbuild_local.toml").write_text(
        'adapter = "failing_duckdb"\n\n'
        "[connection]\n"
        f'database = "{project_dir / "warehouse.duckdb"}"\n'
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert test_case.expected_promote_fragments[0] in (result.stdout + result.stderr)
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT operation_type, status, virtual_environment_name "
            "FROM sqlbuild_state.state_operations WHERE operation_type = 'promote'"
        ),
    ) == [("promote", "failed", "dev")]
    assert query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT status, message FROM sqlbuild_state.state_operation_events "
            "WHERE operation_id LIKE 'promote:%' ORDER BY created_at DESC LIMIT 1"
        ),
    ) == [("failed", test_case.expected_promote_fragments[0])]
    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPromoteE2ETestCase(
            description=(
                "working source blocks whole promotion but allows coherent partial promotion"
            ),
            blocked_command=("promote", "--from", "pr", "--to", "dev"),
            promote_command=(
                "promote",
                "--from",
                "pr",
                "--to",
                "dev",
                "--select",
                "fact_orders",
                "--include-stale-upstreams",
                "--allow-partial-promotion",
            ),
            expected_blocked_fragments=(
                "whole-VDE promotion requires a finalized source virtual environment",
                "--select",
            ),
            expected_promote_fragments=("Virtual promotion complete", "target status"),
            expected_query_results=(
                ("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((2,),)),
                ("SELECT order_count FROM dev__dev.orders_rollup", ((1,),)),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_working_source_vde_when_promoting_then_whole_blocks_and_partial_succeeds(
    test_case: VirtualPromoteE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_promote_working_source",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id")
        | {
            "models/orders_rollup.sql": (
                'MODEL ();\n\nSELECT COUNT(*) AS order_count FROM __ref("fact_orders")\n'
            )
        },
    )
    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"),
        project_dir=project_dir,
    )
    assert init_result.returncode == 0, init_result.stderr
    default_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert default_build_result.returncode == 0, default_build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    branch_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "build",
            "--virtual-env",
            "pr",
            "--select",
            "fact_orders",
            "--include-stale-upstreams",
        ),
        project_dir=project_dir,
    )
    assert branch_build_result.returncode == 0, branch_build_result.stderr

    blocked_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.blocked_command,
        project_dir=project_dir,
    )
    assert blocked_result.returncode == 1, blocked_result.stdout + blocked_result.stderr
    blocked_output: str = blocked_result.stdout + blocked_result.stderr
    fragment: str
    for fragment in test_case.expected_blocked_fragments:
        assert fragment in blocked_output

    promote_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.promote_command,
        project_dir=project_dir,
    )
    assert promote_result.returncode == 0, promote_result.stdout + promote_result.stderr
    for fragment in test_case.expected_promote_fragments:
        assert fragment in promote_result.stdout
    query_sql: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(
            db_path=project_dir / "warehouse.duckdb",
            sql=query_sql,
        ) == list(expected_rows)
