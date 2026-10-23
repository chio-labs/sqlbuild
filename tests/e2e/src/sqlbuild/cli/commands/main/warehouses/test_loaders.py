"""Source loader, dlt and source deferral scenarios shared by every real warehouse."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.load.helpers import (
    build_loader_waffle_shop_project_files,
    build_schema_behavior_project_files,
    write_sqlite_orders_source_database,
)
from tests.e2e.src.sqlbuild.cli.commands.main.warehouses._test_types import (
    DltLoadTestCase,
    IntermediateDagStrategyTestCase,
    LoaderRowsTestCase,
    LoaderStrategiesTestCase,
    LoaderWaffleShopTestCase,
    SourceDeferralTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.warehouses.harness import (
    Rows,
    WarehouseHarness,
    WarehouseSetup,
    on_warehouses,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    run_sqb,
    stringify_warehouse_rows,
)

_DAG_LOADER_SUFFIX: str = (
    "@loader(depends_on=[fetch_events])\n"
    "def raw_events(ctx):\n"
    "    '''Test loader raw_events.'''\n    events = ctx.loader(fetch_events)\n"
    "    cursor = ctx.query(\n"
    "        f'SELECT event_id, amount FROM {events.destination} '\n"
    "        'ORDER BY event_id, amount'\n"
    "    )\n"
    "    rows = cursor.fetchall()\n"
    "    return [{'event_id': row[0], 'amount': row[1]} for row in rows]\n"
)


@pytest.mark.parametrize(
    "warehouse",
    on_warehouses(
        "bigquery",
        WarehouseSetup("snowflake", precreate_schema=False),
        "databricks",
        "postgres",
        "sqlserver",
    ),
    indirect=True,
)
@pytest.mark.parametrize(
    "test_case",
    [
        LoaderStrategiesTestCase(
            description="source loader strategies apply expected rows",
            command=("--no-color", "load", "--concurrency", "4"),
            expected_countries=(("1", "US", "United States"), ("2", "CA", "Canada")),
            expected_webhook_event_counts=(("101", "signup", "2"), ("102", "checkout", "2")),
            expected_order_events=(("201", "1000"), ("202", "2500"), ("203", "3000")),
            expected_customers=(("1", "pro"), ("2", "trial"), ("3", "enterprise")),
            expected_loader_status=(("1", "loaded", "self_managed"),),
            expected_stdout_fragments=("raw_countries", "raw_webhook_events", "raw_customers"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_loader_strategy_project_when_loading_twice_then_write_modes_apply(
    tmp_path: Path,
    warehouse: WarehouseHarness,
    test_case: LoaderStrategiesTestCase,
) -> None:
    project_dir: Path
    schema_name: str
    with warehouse.timing("prepare source loader strategy fixture"):
        project_dir, schema_name = warehouse.prepare_source_loader_strategies(tmp_path)
        warehouse.precreate(schema_name)

    try:
        with warehouse.timing("first sqb load"):
            first_result: subprocess.CompletedProcess[str] = run_sqb(
                command=test_case.command, project_dir=project_dir
            )
        with warehouse.timing("second sqb load"):
            second_result: subprocess.CompletedProcess[str] = run_sqb(
                command=test_case.command, project_dir=project_dir
            )

        assert first_result.returncode == test_case.expected_return_code, (
            first_result.stdout + first_result.stderr
        )
        assert second_result.returncode == test_case.expected_return_code, (
            second_result.stdout + second_result.stderr
        )
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in second_result.stdout

        def rows(columns: str, name: str, tail: str) -> Rows:
            return stringify_warehouse_rows(
                warehouse.fetch_rows(
                    schema_name,
                    f"SELECT {columns} FROM {warehouse.relation(schema_name, name)} {tail}",
                )
            )

        assert (
            rows("country_id, country_code, country_name", "raw_countries", "ORDER BY country_id")
            == test_case.expected_countries
        )
        assert (
            rows(
                "event_id, event_name, COUNT(*)",
                "raw_webhook_events",
                "GROUP BY event_id, event_name ORDER BY event_id",
            )
            == test_case.expected_webhook_event_counts
        )
        assert (
            rows("event_id, amount_cents", "raw_order_events", "ORDER BY event_id")
            == test_case.expected_order_events
        )
        assert (
            rows("customer_id, plan_name", "raw_customers", "ORDER BY customer_id")
            == test_case.expected_customers
        )
        assert (
            rows("status_id, status_name, loaded_by", "raw_loader_status", "ORDER BY status_id")
            == test_case.expected_loader_status
        )
    finally:
        with warehouse.timing("cleanup source loader strategy schema"):
            warehouse.cleanup_schema(schema_name)


@pytest.mark.parametrize(
    "warehouse",
    on_warehouses("bigquery", WarehouseSetup("snowflake", precreate_schema=False)),
    indirect=True,
)
@pytest.mark.parametrize(
    "test_case",
    [
        LoaderRowsTestCase(
            description="source loader schema evolution adds late columns",
            command=("--no-color", "load"),
            expected_rows=(("1", None), ("2", "late-note")),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_loader_schema_evolution_project_when_loading_twice_then_target_evolves(
    tmp_path: Path,
    warehouse: WarehouseHarness,
    test_case: LoaderRowsTestCase,
) -> None:
    schema_name: str = warehouse.unique_schema("sqlbuild_e2e_load_schema")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="source_loader_schema_behavior",
        repo_files=build_schema_behavior_project_files(
            source_yaml=(
                "sources:\n"
                "  - name: raw_events\n    description: Test source raw_events.\n"
                "    managed: true\n"
                "    write_strategy: append\n"
                "    cursor_column: load_seq\n"
                "    columns:\n"
                "      - name: event_id\n"
                "        type: INTEGER\n"
                "      - name: load_seq\n"
                "        type: INTEGER\n"
            ),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def raw_events(ctx):\n"
                "    '''Test loader raw_events.'''\n    if ctx.current_cursor_value is None:\n"
                "        return [{'event_id': 1, 'load_seq': 1}]\n"
                "    return [{'event_id': 2, 'load_seq': 2, 'note': 'late-note'}]\n"
            ),
        ),
    )
    (project_dir / "sqlbuild_project.toml").write_text(
        warehouse.project_toml("source_loader_schema_behavior", schema_name), encoding="utf-8"
    )
    warehouse.precreate(schema_name)

    try:
        first_result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command, project_dir=project_dir
        )
        second_result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command, project_dir=project_dir
        )

        assert first_result.returncode == test_case.expected_return_code, (
            first_result.stdout + first_result.stderr
        )
        assert second_result.returncode == test_case.expected_return_code, (
            second_result.stdout + second_result.stderr
        )
        rows: Rows = warehouse.fetch_rows(
            schema_name,
            "SELECT event_id, note FROM "
            f"{warehouse.relation(schema_name, 'raw_events')} ORDER BY event_id",
        )
        assert stringify_warehouse_rows(rows) == test_case.expected_rows
    finally:
        warehouse.cleanup_schema(schema_name)


@pytest.mark.parametrize(
    "warehouse",
    on_warehouses("bigquery", "snowflake", "postgres", "sqlserver"),
    indirect=True,
)
@pytest.mark.parametrize(
    "test_case",
    [
        LoaderRowsTestCase(
            description="chained source loader runs",
            command=("--no-color", "load", "--select", "+raw_events"),
            expected_rows=(("1", "loaded"), ("2", "loaded")),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_chained_loader_project_when_loading_then_runs_loader_dag(
    tmp_path: Path,
    warehouse: WarehouseHarness,
    test_case: LoaderRowsTestCase,
) -> None:
    schema_name: str = warehouse.unique_schema("sqlbuild_e2e_load_dag")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="source_loader_dag_behavior",
        repo_files=build_schema_behavior_project_files(
            source_yaml=(
                "sources:\n"
                "  - name: raw_events\n    description: Test source raw_events.\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: event_id\n"
                "        type: INTEGER\n"
                "      - name: status\n"
                f"        type: {warehouse.text_type}\n"
            ),
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader(write_strategy='table', columns=[\n"
                "    {'name': 'event_id', 'type': 'INTEGER'},\n"
                "])\n"
                "def fetch_events(ctx):\n"
                "    '''Test loader fetch_events.'''\n    return [{'event_id': 1}, {'event_id': 2}]\n\n"
                "@loader(depends_on=[fetch_events])\n"
                "def raw_events(ctx):\n"
                "    '''Test loader raw_events.'''\n    events = ctx.loader(fetch_events)\n"
                "    cursor = ctx.query(\n"
                "        f'SELECT event_id FROM {events.destination} ORDER BY event_id'\n"
                "    )\n"
                "    rows = cursor.fetchall()\n"
                "    return [{'event_id': row[0], 'status': 'loaded'} for row in rows]\n"
            ),
        ),
    )
    (project_dir / "sqlbuild_project.toml").write_text(
        warehouse.project_toml("source_loader_dag_behavior", schema_name), encoding="utf-8"
    )
    warehouse.precreate(schema_name)

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command, project_dir=project_dir
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        rows: Rows = warehouse.fetch_rows(
            schema_name,
            "SELECT event_id, status FROM "
            f"{warehouse.relation(schema_name, 'raw_events')} ORDER BY event_id",
        )
        assert stringify_warehouse_rows(rows) == test_case.expected_rows
        assert warehouse.row_count(schema_name, "__loader__fetch_events") == 2
    finally:
        warehouse.cleanup_schema(schema_name)


@pytest.mark.parametrize(
    "warehouse",
    on_warehouses("bigquery", "snowflake", "databricks", "postgres", "sqlserver"),
    indirect=True,
)
@pytest.mark.parametrize(
    "test_case",
    [
        IntermediateDagStrategyTestCase(
            description="append intermediate accumulates rows across DAG loads",
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader(write_strategy='append', cursor_column='load_seq', columns=[\n"
                "    {'name': 'event_id', 'type': 'INTEGER'},\n"
                "    {'name': 'amount', 'type': 'INTEGER'},\n"
                "    {'name': 'load_seq', 'type': 'INTEGER'},\n"
                "])\n"
                "def fetch_events(ctx):\n"
                "    '''Test loader fetch_events.'''\n    if ctx.current_cursor_value is None:\n"
                "        next_seq = 1\n"
                "    else:\n"
                "        next_seq = ctx.current_cursor_value + 1\n"
                "    return [\n"
                "        {'event_id': next_seq, 'amount': next_seq * 100, 'load_seq': next_seq}\n"
                "    ]\n\n" + _DAG_LOADER_SUFFIX
            ),
            expected_intermediate_rows=(("1", "100"), ("2", "200")),
            expected_terminal_rows=(("1", "100"), ("2", "200")),
        ),
        IntermediateDagStrategyTestCase(
            description="merge intermediate updates and adds rows across DAG loads",
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader(\n"
                "    write_strategy='merge',\n"
                "    unique_key='event_id',\n"
                "    cursor_column='load_seq',\n"
                "    columns=[\n"
                "        {'name': 'event_id', 'type': 'INTEGER'},\n"
                "        {'name': 'amount', 'type': 'INTEGER'},\n"
                "        {'name': 'load_seq', 'type': 'INTEGER'},\n"
                "    ],\n"
                ")\n"
                "def fetch_events(ctx):\n"
                "    '''Test loader fetch_events.'''\n    if ctx.current_cursor_value is None:\n"
                "        return [\n"
                "            {'event_id': 1, 'amount': 100, 'load_seq': 1},\n"
                "            {'event_id': 2, 'amount': 200, 'load_seq': 1},\n"
                "        ]\n"
                "    return [\n"
                "        {'event_id': 1, 'amount': 150, 'load_seq': 2},\n"
                "        {'event_id': 3, 'amount': 300, 'load_seq': 2},\n"
                "    ]\n\n" + _DAG_LOADER_SUFFIX
            ),
            expected_intermediate_rows=(("1", "150"), ("2", "200"), ("3", "300")),
            expected_terminal_rows=(("1", "150"), ("2", "200"), ("3", "300")),
        ),
        IntermediateDagStrategyTestCase(
            description="delete insert intermediate replaces cursor window across DAG loads",
            loader_py=(
                "from sqlbuild.loaders import loader\n\n"
                "@loader(write_strategy='delete_insert', cursor_column='load_seq', columns=[\n"
                "    {'name': 'event_id', 'type': 'INTEGER'},\n"
                "    {'name': 'amount', 'type': 'INTEGER'},\n"
                "    {'name': 'load_seq', 'type': 'INTEGER'},\n"
                "])\n"
                "def fetch_events(ctx):\n"
                "    '''Test loader fetch_events.'''\n    if ctx.current_cursor_value is None:\n"
                "        return [\n"
                "            {'event_id': 1, 'amount': 100, 'load_seq': 1},\n"
                "            {'event_id': 2, 'amount': 200, 'load_seq': 1},\n"
                "        ]\n"
                "    return [\n"
                "        {'event_id': 2, 'amount': 250, 'load_seq': 1},\n"
                "        {'event_id': 3, 'amount': 300, 'load_seq': 1},\n"
                "    ]\n\n" + _DAG_LOADER_SUFFIX
            ),
            expected_intermediate_rows=(("2", "250"), ("3", "300")),
            expected_terminal_rows=(("2", "250"), ("3", "300")),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_intermediate_strategy_project_when_loading_twice_then_strategy_applies(
    tmp_path: Path,
    warehouse: WarehouseHarness,
    test_case: IntermediateDagStrategyTestCase,
) -> None:
    schema_name: str = warehouse.unique_schema("sqlbuild_e2e_load_dag_strategy")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="source_loader_dag_strategy_behavior",
        repo_files=build_schema_behavior_project_files(
            source_yaml=(
                "sources:\n"
                "  - name: raw_events\n    description: Test source raw_events.\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: event_id\n"
                "        type: INTEGER\n"
                "      - name: amount\n"
                "        type: INTEGER\n"
            ),
            loader_py=test_case.loader_py,
        ),
    )
    (project_dir / "sqlbuild_project.toml").write_text(
        warehouse.project_toml("source_loader_dag_strategy_behavior", schema_name),
        encoding="utf-8",
    )
    warehouse.precreate(schema_name)

    try:
        first_result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command, project_dir=project_dir
        )
        second_result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command, project_dir=project_dir
        )

        assert first_result.returncode == test_case.expected_return_code, (
            first_result.stdout + first_result.stderr
        )
        assert second_result.returncode == test_case.expected_return_code, (
            second_result.stdout + second_result.stderr
        )
        intermediate_rows: Rows = warehouse.fetch_rows(
            schema_name,
            "SELECT event_id, amount FROM "
            f"{warehouse.relation(schema_name, '__loader__fetch_events')} "
            "ORDER BY event_id, amount",
        )
        terminal_rows: Rows = warehouse.fetch_rows(
            schema_name,
            "SELECT event_id, amount FROM "
            f"{warehouse.relation(schema_name, 'raw_events')} ORDER BY event_id, amount",
        )
        assert stringify_warehouse_rows(intermediate_rows) == test_case.expected_intermediate_rows
        assert stringify_warehouse_rows(terminal_rows) == test_case.expected_terminal_rows
    finally:
        warehouse.cleanup_schema(schema_name)


@pytest.mark.parametrize(
    "warehouse",
    on_warehouses("bigquery", "snowflake", "postgres", "sqlserver"),
    indirect=True,
)
@pytest.mark.parametrize(
    "test_case",
    [
        LoaderWaffleShopTestCase(
            description="loader focused waffle shop grows across repeated builds",
            command=("--no-color", "build", "--select", "+customer_revenue"),
            expected_rows=(
                ("1", "pro", "650", "1"),
                ("2", "plus", "3750", "2"),
                ("3", "enterprise", "1300", "1"),
            ),
            expected_stdout_fragments=("loader    fetch_order_events", "source    raw_orders"),
            expected_event_count=4,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_loader_waffle_shop_when_building_then_dag_grows_models(
    tmp_path: Path,
    warehouse: WarehouseHarness,
    test_case: LoaderWaffleShopTestCase,
) -> None:
    schema_name: str = warehouse.unique_schema("sqlbuild_e2e_load_waffle")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="loader_waffle_shop",
        repo_files=build_loader_waffle_shop_project_files(
            project_toml=warehouse.project_toml("loader_waffle_shop", schema_name)
        ),
    )
    warehouse.precreate(schema_name)

    try:
        for _ in range(2):
            result: subprocess.CompletedProcess[str] = run_sqb(
                command=test_case.command, project_dir=project_dir
            )
            assert result.returncode == test_case.expected_return_code, (
                result.stdout + result.stderr
            )
            for fragment in test_case.expected_stdout_fragments:
                assert fragment in result.stdout

        rows: Rows = warehouse.fetch_rows(
            schema_name,
            "SELECT customer_id, plan_name, revenue_cents, order_count FROM "
            f"{warehouse.relation(schema_name, 'customer_revenue')} ORDER BY customer_id",
        )
        assert stringify_warehouse_rows(rows) == test_case.expected_rows
        assert (
            warehouse.row_count(schema_name, "__loader__fetch_order_events")
            == test_case.expected_event_count
        )
    finally:
        warehouse.cleanup_schema(schema_name)


@pytest.mark.parametrize(
    "warehouse",
    on_warehouses(
        "bigquery",
        WarehouseSetup("snowflake", precreate_schema=False),
        "databricks",
        "postgres",
        "sqlserver",
    ),
    indirect=True,
)
@pytest.mark.parametrize(
    "test_case",
    [
        DltLoadTestCase(
            description="loads sqlite dlt source into the raw schema",
            expected_loaded_rows=((1, 10), (2, 20), (3, 30)),
            expected_model_rows=((2, 20), (3, 30)),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_dlt_source_when_loading_then_table_is_materialized_and_queryable(
    tmp_path: Path,
    warehouse: WarehouseHarness,
    test_case: DltLoadTestCase,
) -> None:
    """The raw schema is precreated unless the warehouse leaves its creation to dlt."""

    model_schema_name: str
    raw_schema_name: str
    model_schema_name, raw_schema_name = warehouse.dlt_schemas(
        warehouse.unique_schema(f"sqb_dlt_{warehouse.name}")
    )
    project_name: str = f"dlt_{warehouse.name}_project"
    source_db_path: Path = tmp_path / project_name / "source.db"
    try:
        warehouse.ensure_schema(model_schema_name)
        warehouse.precreate(raw_schema_name)
        project_dir: Path = prepare_inline_project(
            tmp_path=tmp_path,
            project_name=project_name,
            repo_files={
                "sqlbuild_project.toml": warehouse.project_toml(project_name, model_schema_name),
                "sources/raw.yml": (
                    "dlt_sources:\n"
                    "  - type: sql_database\n"
                    f"    schema: {raw_schema_name}\n"
                    "    config:\n"
                    f'      credentials: "sqlite:///{source_db_path}"\n'
                    "    resources:\n"
                    "      - name: raw_orders\n"
                    "        description: Test source raw_orders.\n"
                    "        table: orders\n"
                    "        write_disposition: replace\n"
                ),
                "models/order_totals.sql": (
                    "MODEL (description 'Test model order_totals.', materialized table);\n\n"
                    'SELECT order_id, amount FROM __source("raw_orders") WHERE amount >= 20\n'
                ),
            },
        )
        write_sqlite_orders_source_database(source_db_path)

        load_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "load", "--select", "raw_orders"), project_dir=project_dir
        )

        assert load_result.returncode == test_case.expected_return_code, (
            load_result.stdout + load_result.stderr
        )
        loaded_rows: Rows = warehouse.fetch_rows(
            raw_schema_name,
            "SELECT order_id, amount FROM "
            f"{warehouse.relation(raw_schema_name, 'raw_orders')} ORDER BY order_id",
        )
        assert loaded_rows == test_case.expected_loaded_rows

        build_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build", "--select", "order_totals"), project_dir=project_dir
        )

        assert build_result.returncode == test_case.expected_return_code, (
            build_result.stdout + build_result.stderr
        )
        model_rows: Rows = warehouse.fetch_rows(
            model_schema_name,
            "SELECT order_id, amount FROM "
            f"{warehouse.relation(model_schema_name, 'order_totals')} ORDER BY order_id",
        )
        assert model_rows == test_case.expected_model_rows
    finally:
        warehouse.cleanup_schema(raw_schema_name)
        warehouse.cleanup_schema(model_schema_name)


@pytest.mark.parametrize(
    "warehouse",
    on_warehouses("bigquery", "snowflake", "postgres", "sqlserver"),
    indirect=True,
)
@pytest.mark.parametrize(
    "test_case",
    [
        SourceDeferralTestCase(
            description="loader writes dev while model reads prod deferred source",
            expected_model_rows=(("99", "prod-source"),),
            expected_loader_rows=(("7", "loaded-dev"),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_source_deferral_env_when_building_then_reads_prod_and_writes_dev(
    tmp_path: Path,
    warehouse: WarehouseHarness,
    test_case: SourceDeferralTestCase,
) -> None:
    dev_schema_name: str = warehouse.unique_schema("sqlbuild_e2e_defer_dev")
    prod_schema_name: str = warehouse.unique_schema("sqlbuild_e2e_defer_prod")
    project_name: str = f"{warehouse.name}_source_deferral"
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": warehouse.source_deferral_project_toml(
                project_name, dev_schema_name, prod_schema_name
            ),
            **warehouse.local_files(dev_schema_name),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n    description: Test source raw_orders.\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
                "      - name: status\n"
                f"        type: {warehouse.deferral_text_type}\n"
            ),
            "python/loaders/raw_orders.py": (
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def raw_orders(ctx):\n"
                "    '''Test loader raw_orders.'''\n    return [{'order_id': 7, 'status': 'loaded-dev'}]\n"
            ),
            "models/stg_orders.sql": (
                'MODEL (description "Test model stg_orders.", materialized table);\n\nSELECT order_id, status FROM __source("raw_orders")'
            ),
        },
    )
    warehouse.ensure_schema(dev_schema_name)
    warehouse.ensure_schema(prod_schema_name)

    try:
        for statement in warehouse.seed_statements(
            warehouse.relation(prod_schema_name, "raw_orders"),
            f"order_id INTEGER, status {warehouse.text_type}",
            "(99, 'prod-source')",
            "SELECT 99 AS order_id, 'prod-source' AS status",
        ):
            warehouse.execute_sql(prod_schema_name, statement)

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command, project_dir=project_dir
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        model_rows: Rows = warehouse.fetch_rows(
            dev_schema_name,
            "SELECT order_id, status FROM "
            f"{warehouse.relation(dev_schema_name, 'stg_orders')} ORDER BY order_id",
        )
        loader_rows: Rows = warehouse.fetch_rows(
            dev_schema_name,
            "SELECT order_id, status FROM "
            f"{warehouse.relation(dev_schema_name, 'raw_orders')} ORDER BY order_id",
        )
        assert stringify_warehouse_rows(model_rows) == test_case.expected_model_rows
        assert stringify_warehouse_rows(loader_rows) == test_case.expected_loader_rows
    finally:
        warehouse.cleanup_schema(dev_schema_name)
        warehouse.cleanup_schema(prod_schema_name)
