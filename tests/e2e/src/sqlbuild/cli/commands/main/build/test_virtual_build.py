from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    VirtualBuildE2ETestCase,
    VirtualBuildSelectionGuardE2ETestCase,
    VirtualCustomMaterializationE2ETestCase,
    VirtualExplicitCheckpointRollbackE2ETestCase,
    VirtualPartialRollbackE2ETestCase,
    VirtualPromoteE2ETestCase,
    VirtualPythonBuildE2ETestCase,
    VirtualRollbackE2ETestCase,
    VirtualWaffleShopE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import (
    initialize_virtual_seeded_project,
    prepare_virtual_seeded_incremental_project,
    rewrite_incremental_orders_model,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_virtual_plan_project_toml,
    build_virtual_plan_repo_files,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
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
    ids=["runs loader-side and read-side Python nodes"],
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
                'environment_mode = "virtual"\n'
                'default_environment = "dev"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[environments.dev]\n"
                'schema = "dev"\n'
                'defer_sources_to = "dev"\n\n'
                "[environments.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n\n'
                "[environments.dev.state.connection]\n"
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
                "def load_raw_orders(ctx):\n"
                "    marker = Path(__file__).parents[1].joinpath('prepared.txt')\n"
                "    return [{'order_id': int(marker.read_text())}]\n"
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    loader: load_raw_orders\n"
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
    ids=["prints read-side Python failure rows"],
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
                'environment_mode = "virtual"\n'
                'default_environment = "dev"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[environments.dev]\n"
                'schema = "dev"\n\n'
                "[environments.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n\n'
                "[environments.dev.state.connection]\n"
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
    ids=["no-python only runs loader-side Python nodes"],
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
                'environment_mode = "virtual"\n'
                'default_environment = "dev"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[environments.dev]\n"
                'schema = "dev"\n'
                'defer_sources_to = "dev"\n\n'
                "[environments.dev.state]\n"
                'backend = "duckdb"\n'
                'schema = "sqlbuild_state"\n\n'
                "[environments.dev.state.connection]\n"
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
                "def load_raw_orders(ctx):\n"
                "    marker = Path(__file__).parents[1].joinpath('prepared.txt')\n"
                "    return [{'order_id': int(marker.read_text())}]\n"
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    loader: load_raw_orders\n"
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
    ids=["delete-insert incremental seeds new physical version from prior version"],
)
def test_given_virtual_incremental_change_when_building_then_it_seeds_new_physical_version(
    test_case: VirtualBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_virtual_seeded_incremental_project(
        tmp_path=tmp_path,
        project_name="virtual_seeded_delete_insert",
        incremental_strategy="delete_insert",
        query_change_backfill="bounded-7d",
    )
    initialize_virtual_seeded_project(project_dir=project_dir)

    rewrite_incremental_orders_model(
        project_dir=project_dir,
        incremental_strategy="delete_insert",
        query_change_backfill="bounded-7d",
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
    ids=["custom materialization prepare_version seeds changed physical target"],
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
)
from sqlbuild.virtual.executor.models import VersionPrepareContext


def prepare_version(ctx: VersionPrepareContext) -> None:
    ctx.execute_sql(
        f"CREATE TABLE {ctx.target} AS "
        f"SELECT id, amount_cents, 'prepared' AS version_marker FROM {ctx.prior_relation}"
    )


def materialize(ctx: MaterializationContext) -> MaterializationResult:
    incoming = (
        "SELECT id, amount_cents, 'materialized' AS version_marker "
        f"FROM ({ctx.sql}) AS model_sql"
    )
    exists = ctx.adapter.relation_exists(
        ctx.connection,
        database=ctx.target_database,
        schema=ctx.target_schema,
        name=ctx.target_name,
    )
    if not exists:
        ctx.execute_sql(f"CREATE TABLE {ctx.target} AS {incoming}")
    else:
        ctx.execute_sql(
            f"DELETE FROM {ctx.target} WHERE id IN "
            f"(SELECT id FROM ({ctx.sql}) AS model_sql)"
        )
        ctx.execute_sql(f"INSERT INTO {ctx.target} {incoming}")
    return MaterializationResult(relation=ctx.target)
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
    ids=["full waffle shop fixture builds in virtual mode"],
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
environment_mode = "virtual"
default_environment = "dev"

[connection]
database = "waffle_shop.duckdb"

[settings]
default_audit_severity = "warn"

[defaults]
materialized = "table"

[path_defaults.staging]
materialized = "view"

[environments.dev]
schema = "dev"
defer_sources_to = "dev"

[environments.dev.state]
backend = "duckdb"
schema = "sqlbuild_state"

[environments.dev.state.connection]
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
        str(asset["name"]): asset for asset in assets if asset.get("kind") == "function"
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
    ids=["append bounded incremental seeds only rows before replay window"],
)
def test_given_virtual_append_bounded_change_when_building_then_seed_excludes_replay_window(
    test_case: VirtualBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_virtual_seeded_incremental_project(
        tmp_path=tmp_path,
        project_name="virtual_seeded_append",
        incremental_strategy="append",
        query_change_backfill="bounded-7d",
    )
    initialize_virtual_seeded_project(project_dir=project_dir)

    rewrite_incremental_orders_model(
        project_dir=project_dir,
        incremental_strategy="append",
        query_change_backfill="bounded-7d",
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
    ids=["rollback blocks when checkpoint physical relation is missing"],
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
            "JOIN sqlbuild_state.virtual_environment_checkpoint_refs cr "
            "ON cp.checkpoint_id = cr.checkpoint_id "
            "JOIN sqlbuild_state.physical_relations pr "
            "ON pr.model_name = cr.model_name AND pr.version_hash = cr.version_hash "
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
    ids=["rollback blocks when no previous checkpoint exists"],
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
    ids=["rollback blocks when target VDE lock exists"],
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
    ids=["checkpoint show blocks for unknown checkpoint"],
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
    ids=["whole VDE promotion swaps target refs and views"],
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
    ids=["whole VDE promotion carries function definitions"],
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
                "query_change_backfill full);\n\n"
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
        "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, query_change_backfill full);\n\n"
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
            "SELECT function_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_function_refs "
            "WHERE virtual_environment_name = 'dev'"
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
    ids=["whole VDE rollback restores previous finalized checkpoint"],
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
            "SELECT model_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_refs "
            "WHERE virtual_environment_name = 'dev' ORDER BY model_name"
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
            "SELECT model_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_refs "
            "WHERE virtual_environment_name = 'dev' ORDER BY model_name"
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
    ids=["whole VDE rollback restores checkpointed function definitions"],
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
                "query_change_backfill full);\n\n"
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
        "FUNCTION (arguments (amount INTEGER), returns BOOLEAN, query_change_backfill full);\n\n"
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
    ids=["explicit checkpoint restores selected checkpoint"],
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
    ids=["partial rollback requires override and marks VDE working"],
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
    ids=["partial rollback can include stale required upstreams"],
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
    ids=["partial rollback matches checkpoint when workspace changed"],
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
    ids=["finalized source promotes after workspace changes again"],
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
    ids=["partial promotion requires explicit working target acceptance"],
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
            description="direct mode promotion fails with mode error",
            promote_command=("promote", "--from", "pr", "--to", "dev"),
            expected_promote_fragments=("promote requires environment_mode = 'virtual'",),
            expected_query_results=(),
        )
    ],
    ids=["direct mode promotion fails with mode error"],
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
                'default_environment = "dev"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[environments.dev]\n"
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
    ids=["missing promoted physical relation fails clearly"],
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
            "WHERE model_name = 'fact_orders' "
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
    ids=["target VDE lock blocks promotion"],
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
    ids=["interrupted promotion records failed operation"],
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
                "from sqlbuild.adapter.shared.models import StatementRecorder\n"
                "from sqlbuild.adapter.shared.exceptions import AdapterUserError\n"
                "from sqlbuild.adapters.duckdb.client import DuckDbAdapter\n\n"
                "class FailingDuckDbAdapter(DuckDbAdapter):\n"
                "    adapter_name = 'failing_duckdb'\n\n"
                "    def create_view_as(\n"
                "        self,\n"
                "        connection: Any,\n"
                "        *,\n"
                "        target: str,\n"
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
    ids=["working source blocks whole promotion but allows coherent partial promotion"],
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
