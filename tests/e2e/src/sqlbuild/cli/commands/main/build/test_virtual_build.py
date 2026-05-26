from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    VirtualBuildE2ETestCase,
    VirtualBuildSelectionGuardE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_virtual_plan_repo_files,
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
        VirtualBuildE2ETestCase(
            description="default VDE creates physical versions and queryable views",
            expected_build_fragments=("Virtual environment", "name: dev"),
            expected_plan_fragments=("Plan ready (0 selected)", "status: finalized"),
            expected_query_results=(("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((7,),)),),
            expected_ref_rows=(("dim_customers",), ("fact_orders",), ("stg_orders",)),
            expected_physical_version_count=3,
        )
    ],
    ids=["default VDE creates physical versions and queryable views"],
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
            "SELECT model_name FROM sqlbuild_state.virtual_environment_refs "
            "WHERE virtual_environment_name = 'dev' ORDER BY model_name"
        ),
    )
    assert ref_rows == list(test_case.expected_ref_rows)
    ref_hash_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT model_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_refs "
            "WHERE virtual_environment_name = 'dev' ORDER BY model_name"
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
            "SELECT model_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_refs "
            "WHERE virtual_environment_name = 'dev' ORDER BY model_name"
        ),
    )
    assert repeat_ref_hash_rows == ref_hash_rows


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
    ids=["explicit VDE graph selection diverges refs and leaves downstream working"],
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
            "SELECT dev.model_name "
            "FROM sqlbuild_state.virtual_environment_refs dev "
            "JOIN sqlbuild_state.virtual_environment_refs kevin "
            "ON dev.model_name = kevin.model_name "
            "WHERE dev.virtual_environment_name = 'dev' "
            "AND kevin.virtual_environment_name = 'kevin' "
            "AND dev.version_hash <> kevin.version_hash "
            "ORDER BY dev.model_name"
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
    ids=["selected downstream with stale upstream blocks then expands"],
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
