from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    VirtualBuildE2ETestCase,
    VirtualCustomMaterializationE2ETestCase,
    VirtualWaffleShopE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import (
    initialize_virtual_seeded_project,
    prepare_virtual_cursor_override_without_snapshot_project,
    prepare_virtual_seeded_incremental_project,
    rewrite_cursor_override_without_snapshot_model,
    rewrite_incremental_orders_model,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_virtual_plan_project_toml,
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
    assets_by_name: dict[str, dict[str, object]] = {str(asset["name"]): asset for asset in assets}
    assert len(assets_by_name) == len(assets)
    function_name: str
    for function_name in test_case.expected_function_names:
        assert assets_by_name[function_name]["kind"] in {"udf", "table_fn"}
        assert assets_by_name[function_name]["status"] == "success"

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
