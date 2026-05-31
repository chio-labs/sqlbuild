"""E2E tests for sqb build command."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    BuildE2ETestCase,
    PythonBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    prepare_waffle_shop,
    query_duckdb,
    run_sqb,
    table_exists,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PythonBuildE2ETestCase(
            description="build executes full Python SQL Python spine in lifecycle order",
            expected_exit_code=0,
            expected_execution_fragments=(
                "Python ingress (2)",
                "Python read-side (3)",
                "python    task      prepare_orders",
                "python    asset     publish_prepared_orders",
                "python    task      profile_fact_orders",
                "python    asset     export_fact_orders",
                "python    task      notify_fact_orders",
            ),
            expected_table_names=("window_orders", "raw_orders", "fact_orders"),
            expected_notify_text="7",
            expected_fact_orders_rows=((7,),),
        )
    ],
    ids=["build executes full Python SQL Python spine in lifecycle order"],
)
def test_given_python_sql_python_spine_when_building_then_orders_python_around_sql(
    test_case: PythonBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="python_sql_python_spine_build_project",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "python_sql_python_spine_build_project"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "python_sql_python_spine_build_project.duckdb"\n'
            ),
            "loaders/window.py": (
                "from sqlbuild.loaders import loader\n\n"
                "@loader(\n"
                "    target='window_orders',\n"
                "    write_strategy='table',\n"
                "    columns=[{'name': 'order_id', 'type': 'INTEGER'}],\n"
                ")\n"
                "def load_window_orders(ctx):\n"
                "    return [{'order_id': 7}]\n"
            ),
            "tasks/prepare.py": (
                "from loaders.window import load_window_orders\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=load_window_orders)\n"
                "def prepare_orders(ctx):\n"
                "    rows = ctx.query('SELECT order_id FROM window_orders').fetchall()\n"
                "    return ctx.result(payload={'order_id': rows[0][0]})\n"
            ),
            "assets/prepare.py": (
                "from pathlib import Path\n"
                "from tasks.prepare import prepare_orders\n"
                "from sqlbuild.assets import asset\n\n"
                "@asset(depends_on=prepare_orders)\n"
                "def publish_prepared_orders(ctx):\n"
                "    payload = ctx.payload(prepare_orders)\n"
                "    marker = Path(__file__).parents[1].joinpath('prepared_order_id.txt')\n"
                "    marker.write_text(str(payload['order_id']))\n"
                "    return ctx.result(payload=payload, materialized=True)\n"
            ),
            "loaders/raw.py": (
                "from pathlib import Path\n"
                "from assets.prepare import publish_prepared_orders\n"
                "from sqlbuild.loaders import loader\n\n"
                "@loader(depends_on=(publish_prepared_orders,))\n"
                "def load_raw_orders(ctx):\n"
                "    marker = Path(__file__).parents[1].joinpath('prepared_order_id.txt')\n"
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
                "from sqlbuild.refs import model\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=model('fact_orders'))\n"
                "def profile_fact_orders(ctx):\n"
                "    relation = ctx.relation(model('fact_orders'))\n"
                "    order_id = ctx.query(f'SELECT order_id FROM {relation}').fetchall()[0][0]\n"
                "    return ctx.result(payload={'order_id': order_id}, metadata={'rows': 1})\n"
            ),
            "assets/export.py": (
                "from tasks.profile import profile_fact_orders\n"
                "from sqlbuild.assets import asset\n\n"
                "@asset(depends_on=profile_fact_orders)\n"
                "def export_fact_orders(ctx):\n"
                "    payload = ctx.payload(profile_fact_orders)\n"
                "    return ctx.result(payload=payload, metadata={'exported': True})\n"
            ),
            "tasks/notify.py": (
                "from pathlib import Path\n"
                "from assets.export import export_fact_orders\n"
                "from sqlbuild.tasks import task\n\n"
                "@task(depends_on=export_fact_orders)\n"
                "def notify_fact_orders(ctx):\n"
                "    payload = ctx.payload(export_fact_orders)\n"
                "    output = Path(__file__).parents[1].joinpath('notify.txt')\n"
                "    output.write_text(str(payload['order_id']))\n"
                "    return ctx.result(metadata={'notified': True})\n"
            ),
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "+fact_orders +notify_fact_orders"),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_execution_fragments:
        assert fragment in result.stdout
    execution_output: str = result.stdout[result.stdout.index("Execution  sqb build") :]
    assert execution_output.index("window_orders") < execution_output.index("prepare_orders")
    assert execution_output.index("prepare_orders") < execution_output.index(
        "publish_prepared_orders"
    )
    assert execution_output.index("raw_orders") < execution_output.index("fact_orders")
    assert execution_output.index("fact_orders") < execution_output.index("profile_fact_orders")
    assert execution_output.index("profile_fact_orders") < execution_output.index(
        "export_fact_orders"
    )
    assert execution_output.index("export_fact_orders") < execution_output.index(
        "notify_fact_orders"
    )
    assert (project_dir / "notify.txt").read_text(encoding="utf-8") == (
        test_case.expected_notify_text
    )
    db_path: Path = project_dir / "python_sql_python_spine_build_project.duckdb"
    table_name: str
    for table_name in test_case.expected_table_names:
        assert table_exists(db_path=db_path, table_name=table_name)
    rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT order_id FROM fact_orders",
    )
    assert tuple(rows) == test_case.expected_fact_orders_rows


@pytest.mark.parametrize(
    "test_case",
    [
        BuildE2ETestCase(
            description="build materializes all tables views and seeds with correct data",
            expected_exit_code=0,
            expected_table_names=(
                "daily_order_partitioned",
                "daily_revenue",
                "dim_customers",
                "fact_orders",
            ),
            expected_view_names=("stg_customers", "stg_orders", "stg_payments"),
            expected_seed_names=("waffle_types",),
            expected_fact_orders_data=(
                (1, 1, "Classic Belgian", "completed"),
                (2, 1, "Cheddar Herb", "completed"),
                (3, 2, "Chicken and Waffle", "completed"),
                (4, 3, "Liege", "completed"),
                (5, 4, "Classic Belgian", "completed"),
                (6, 4, "Brussels", "completed"),
                (7, 5, "Everything Bagel", "cancelled"),
                (8, 1, "Liege", "completed"),
                (9, 2, "Chicken and Waffle", "preparing"),
                (10, 3, "Classic Belgian", "placed"),
            ),
            expected_fact_orders_python_udf_data=((1, True), (10, False)),
            expected_customer_orders_table_function_data=(
                (1, "Classic Belgian", 1700, "completed", True),
                (2, "Cheddar Herb", 1050, "completed", True),
                (8, "Liege", 950, "completed", True),
            ),
            expected_dim_customers_data=(
                (1, "Leslie", 3, 3700),
                (2, "Ron", 2, 4350),
                (3, "Ann", 2, 950),
                (4, "Ben", 2, 1600),
                (5, "April", 1, 0),
            ),
            expected_waffle_types_data=(
                (1, "Classic Belgian", "sweet", 850),
                (2, "Liege", "sweet", 950),
                (3, "Brussels", "sweet", 750),
                (4, "Cheddar Herb", "savory", 1050),
                (5, "Everything Bagel", "savory", 1100),
                (6, "Chicken and Waffle", "savory", 1450),
            ),
            expected_daily_revenue_data=(
                ("2026-04-01", 3, 6, 7100),
                ("2026-04-02", 3, 3, 2550),
                ("2026-04-03", 1, 1, 950),
            ),
            expected_daily_order_partitioned_data=(
                ("2026-04-01", 3, 6, 2),
                ("2026-04-02", 3, 3, 2),
                ("2026-04-03", 2, 3, 2),
                ("2026-04-04", 2, 6, 2),
            ),
        ),
    ],
    ids=["build materializes all tables views and seeds with correct data"],
)
def test_given_waffle_shop_project_when_running_build_then_warehouse_state_matches_expected(
    test_case: BuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)
    db_path: Path = project_dir / "waffle_shop.duckdb"

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    run_sql_path: Path = project_dir / "target" / "run" / "models" / "marts" / "fact_orders.sql"
    assert run_sql_path.exists()
    run_sql: str = run_sql_path.read_text(encoding="utf-8")
    assert "CREATE OR REPLACE TABLE main.fact_orders__staging AS" in run_sql
    assert "ALTER TABLE main.fact_orders__staging RENAME TO fact_orders;" in run_sql

    table_name: str
    for table_name in test_case.expected_table_names:
        assert table_exists(db_path=db_path, table_name=table_name), (
            f"table {table_name} should exist"
        )

    view_name: str
    for view_name in test_case.expected_view_names:
        assert table_exists(db_path=db_path, table_name=view_name), f"view {view_name} should exist"

    seed_name: str
    for seed_name in test_case.expected_seed_names:
        assert table_exists(db_path=db_path, table_name=seed_name), f"seed {seed_name} should exist"

    fact_sql: str = (
        "SELECT order_id, customer_id, waffle_name, order_status "
        "FROM main.fact_orders ORDER BY order_id"
    )
    fact_rows: list[tuple[Any, ...]] = query_duckdb(db_path=db_path, sql=fact_sql)
    assert tuple(tuple(r) for r in fact_rows) == test_case.expected_fact_orders_data

    python_udf_sql: str = (
        "SELECT order_id, is_completed_order_py FROM main.fact_orders "
        "WHERE order_id IN (1, 10) ORDER BY order_id"
    )
    python_udf_rows: list[tuple[Any, ...]] = query_duckdb(db_path=db_path, sql=python_udf_sql)
    assert (
        tuple(tuple(r) for r in python_udf_rows) == test_case.expected_fact_orders_python_udf_data
    )

    table_function_sql: str = (
        "SELECT order_id, waffle_name, line_total_cents, order_status, is_completed_order "
        "FROM main.customer_orders(1) ORDER BY order_id"
    )
    table_function_rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=db_path, sql=table_function_sql
    )
    assert (
        tuple(tuple(r) for r in table_function_rows)
        == test_case.expected_customer_orders_table_function_data
    )

    dim_sql: str = (
        "SELECT customer_id, first_name, lifetime_orders, lifetime_spend_cents "
        "FROM main.dim_customers ORDER BY customer_id"
    )
    dim_rows: list[tuple[Any, ...]] = query_duckdb(db_path=db_path, sql=dim_sql)
    assert tuple(tuple(r) for r in dim_rows) == test_case.expected_dim_customers_data

    seed_sql: str = (
        "SELECT waffle_type_id, waffle_name, category, price_cents "
        "FROM main.waffle_types ORDER BY waffle_type_id"
    )
    seed_rows: list[tuple[Any, ...]] = query_duckdb(db_path=db_path, sql=seed_sql)
    assert tuple(tuple(r) for r in seed_rows) == test_case.expected_waffle_types_data

    revenue_sql: str = (
        "SELECT CAST(revenue_date AS VARCHAR), order_count, "
        "waffles_sold, total_revenue_cents "
        "FROM main.daily_revenue ORDER BY revenue_date"
    )
    revenue_rows: list[tuple[Any, ...]] = query_duckdb(db_path=db_path, sql=revenue_sql)
    assert tuple(tuple(r) for r in revenue_rows) == test_case.expected_daily_revenue_data

    partitioned_sql: str = (
        "SELECT CAST(order_date AS VARCHAR), order_count, "
        "waffles_ordered, unique_customers "
        "FROM main.daily_order_partitioned ORDER BY order_date"
    )
    partitioned_rows: list[tuple[Any, ...]] = query_duckdb(db_path=db_path, sql=partitioned_sql)
    assert (
        tuple(tuple(r) for r in partitioned_rows) == test_case.expected_daily_order_partitioned_data
    )
