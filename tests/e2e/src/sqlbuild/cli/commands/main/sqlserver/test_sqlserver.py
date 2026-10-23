from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.sqlserver._test_types import (
    SqlServerBuildE2ETestCase,
    SqlServerCloneE2ETestCase,
    SqlServerDbtProfileE2ETestCase,
    SqlServerDiffE2ETestCase,
    SqlServerSourceLoaderE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.sqlserver.helpers import (
    build_sqlserver_config,
    build_sqlserver_project_toml,
    build_unique_schema_name,
    cleanup_sqlserver_schema,
    ensure_sqlserver_schema_ready,
    execute_sqlserver_sql,
    fetch_sqlserver_rows,
    prepare_sqlserver_waffle_shop,
    relation_name,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    assert_dbt_profile_lifecycle,
    prepare_inline_project,
    run_sqb,
    stringify_warehouse_rows,
)


@pytest.mark.parametrize(
    "test_case",
    (
        SqlServerCloneE2ETestCase(
            description="managed source is copied before dependent view recreation",
            expected_stdout_fragments=(
                "raw_customers",
                "copied",
                "stg_customers",
                "recreated_view",
            ),
            expected_rows=((1, "Ada"), (2, "Grace")),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_managed_source_when_cloning_sqlserver_then_source_precedes_dependent_view(
    test_case: SqlServerCloneE2ETestCase,
    tmp_path: Path,
) -> None:
    config: dict[str, object] = build_sqlserver_config()
    schema_base: str = build_unique_schema_name(prefix="sqb_clone_source")
    dev_schema_name: str = f"{schema_base}_dev"
    prod_schema_name: str = f"{schema_base}_prod"
    dev_loader_schema_name: str = f"{schema_base}_raw_dev"
    prod_loader_schema_name: str = f"{schema_base}_raw_prod"
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="sqlserver_managed_source_clone",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "sqlserver_managed_source_clone"\n'
                'adapter = "sqlserver"\n'
                'default_target = "dev"\n\n'
                "[connection]\n"
                f'host = "{config["host"]}"\n'
                f"port = {config['port']}\n"
                f'database = "{config["database"]}"\n'
                f'user = "{config["user"]}"\n'
                f'password = "{config["password"]}"\n\n'
                "[targets.dev]\n"
                f'schema = "{dev_schema_name}"\n\n'
                f'loader_schema = "{dev_loader_schema_name}"\n\n'
                "[targets.dev.clone]\n"
                "allow_as_clone_origin = true\n\n"
                "[targets.prod]\n"
                f'schema = "{prod_schema_name}"\n\n'
                f'loader_schema = "{prod_loader_schema_name}"\n\n'
                "[targets.prod.clone]\n"
                "allow_as_clone_destination = true\n"
            ),
            "python/loaders/raw.py": (
                "from sqlbuild.loaders import loader\n\n"
                "@loader\n"
                "def raw_customers(ctx):\n"
                "    '''Test loader raw_customers.'''\n    return []\n"
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_customers\n    description: Test source raw_customers.\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: customer_id\n"
                "        type: INTEGER\n"
                "      - name: first_name\n"
                "        type: VARCHAR\n"
            ),
            "models/stg_customers.sql": (
                "MODEL (description 'Test model stg_customers.', materialized view);\n\n"
                'SELECT customer_id, first_name FROM __source("raw_customers")\n'
            ),
        },
    )
    try:
        ensure_sqlserver_schema_ready(schema_name=dev_schema_name, config=config)
        ensure_sqlserver_schema_ready(schema_name=prod_schema_name, config=config)
        ensure_sqlserver_schema_ready(schema_name=dev_loader_schema_name, config=config)
        ensure_sqlserver_schema_ready(schema_name=prod_loader_schema_name, config=config)
        execute_sqlserver_sql(
            sql=(
                "SELECT customer_id, first_name "
                f"INTO {relation_name(schema_name=dev_loader_schema_name, name='raw_customers')} "
                "FROM (VALUES (1, 'Ada'), (2, 'Grace')) AS source(customer_id, first_name)"
            ),
            config=config,
        )
        execute_sqlserver_sql(
            sql=(
                f"CREATE VIEW {relation_name(schema_name=dev_schema_name, name='stg_customers')} "
                "AS SELECT customer_id, first_name "
                f"FROM {relation_name(schema_name=dev_loader_schema_name, name='raw_customers')}"
            ),
            config=config,
        )

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "clone", "--from", "dev", "--to", "prod"),
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        expected_fragment: str
        for expected_fragment in test_case.expected_stdout_fragments:
            assert expected_fragment in result.stdout
        assert (
            fetch_sqlserver_rows(
                sql=(
                    "SELECT customer_id, first_name FROM "
                    f"{relation_name(schema_name=prod_schema_name, name='stg_customers')} "
                    "ORDER BY customer_id"
                ),
                config=config,
            )
            == test_case.expected_rows
        )
    finally:
        cleanup_sqlserver_schema(schema_name=prod_loader_schema_name, config=config)
        cleanup_sqlserver_schema(schema_name=dev_loader_schema_name, config=config)
        cleanup_sqlserver_schema(schema_name=prod_schema_name, config=config)
        cleanup_sqlserver_schema(schema_name=dev_schema_name, config=config)


@pytest.mark.parametrize(
    "test_case",
    (
        SqlServerDiffE2ETestCase(
            description="schema-only diff ignores row drift",
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--schema-only",
                "--select",
                "fact_orders",
            ),
            mutation_sql=("UPDATE {dev} SET amount_cents = 105 WHERE order_id = 1",),
            expected_stdout_fragments=("fact_orders", "No schema differences."),
            expected_return_code=0,
        ),
        SqlServerDiffE2ETestCase(
            description="full diff reports row mismatch",
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--full",
                "--select",
                "fact_orders",
            ),
            mutation_sql=("UPDATE {dev} SET amount_cents = 105 WHERE order_id = 1",),
            expected_stdout_fragments=(
                "amount_cents",
                "mismatches=1",
                "order_id=1 | 100 -> 105",
            ),
            expected_return_code=1,
        ),
        SqlServerDiffE2ETestCase(
            description="same-target full diff reports identical rows",
            command=(
                "--no-color",
                "diff",
                "dev:dev",
                "--full",
                "--select",
                "fact_orders",
            ),
            mutation_sql=(),
            expected_stdout_fragments=(
                "fact_orders",
                "No schema differences.",
                "No changed columns.",
            ),
            expected_return_code=0,
        ),
        SqlServerDiffE2ETestCase(
            description="bounded diff filters rows below integer cursor bound",
            command=(
                "--no-color",
                "diff",
                "prod:dev",
                "--bounded",
                "2",
                "--select",
                "fact_orders",
            ),
            mutation_sql=(
                "UPDATE {dev} SET amount_cents = 105 WHERE order_id = 1",
                "UPDATE {dev} SET amount_cents = 205 WHERE order_id = 2",
            ),
            expected_stdout_fragments=(
                "amount_cents",
                "mismatches=1",
                "order_id=2 | 200 -> 205",
            ),
            expected_absent_stdout_fragments=("order_id=1 | 100 -> 105",),
            expected_return_code=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_sqlserver_targets_when_running_diff_then_all_modes_execute_end_to_end(
    test_case: SqlServerDiffE2ETestCase,
    tmp_path: Path,
) -> None:
    config: dict[str, object] = build_sqlserver_config()
    prod_schema: str = build_unique_schema_name(prefix="sqb_diff_prod")
    dev_schema: str = build_unique_schema_name(prefix="sqb_diff_dev")
    ensure_sqlserver_schema_ready(schema_name=prod_schema, config=config)
    ensure_sqlserver_schema_ready(schema_name=dev_schema, config=config)
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="sqlserver_diff_project",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "sqlserver_diff_project"\n'
                'adapter = "sqlserver"\n'
                'default_target = "dev"\n\n'
                "[connection]\n"
                f'host = "{config["host"]}"\n'
                f"port = {config['port']}\n"
                f'database = "{config["database"]}"\n'
                f'user = "{config["user"]}"\n'
                f'password = "{config["password"]}"\n\n'
                "[targets.prod]\n"
                f'schema = "{prod_schema}"\n\n'
                "[targets.dev]\n"
                f'schema = "{dev_schema}"\n'
            ),
            "models/fact_orders.sql": (
                "MODEL (description 'Test model fact_orders.',\n"
                "  materialized table,\n"
                "  unique_key [order_id],\n"
                "  cursor order_id,\n"
                "  cursor_type integer,\n"
                ");\n\n"
                "SELECT 1 AS order_id, 100 AS amount_cents\n"
            ),
        },
    )
    prod_relation: str = relation_name(schema_name=prod_schema, name="fact_orders")
    dev_relation: str = relation_name(schema_name=dev_schema, name="fact_orders")

    try:
        for relation in (prod_relation, dev_relation):
            execute_sqlserver_sql(
                config=config,
                sql=f"CREATE TABLE {relation} (order_id INT, amount_cents INT); "
                f"INSERT INTO {relation} VALUES (1, 100), (2, 200), (3, 300)",
            )
        for mutation_sql in test_case.mutation_sql:
            execute_sqlserver_sql(sql=mutation_sql.format(dev=dev_relation), config=config)

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout, result.stdout + result.stderr
        for fragment in test_case.expected_absent_stdout_fragments:
            assert fragment not in result.stdout, result.stdout + result.stderr
    finally:
        cleanup_sqlserver_schema(schema_name=dev_schema, config=config)
        cleanup_sqlserver_schema(schema_name=prod_schema, config=config)


@pytest.mark.dbt
@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerDbtProfileE2ETestCase(
            description="dbt init generated project builds through SQL Server dbt profile",
            schema_prefix="sqlbuild_dbt_profile",
            expected_toml_fragments=(
                'adapter = "sqlserver"',
                'source = "dbt_profile"',
                'profile = "analytics"',
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sqlserver_dbt_profile_when_running_dbt_init_then_builds_profile_lifecycle(
    tmp_path: Path,
    test_case: SqlServerDbtProfileE2ETestCase,
) -> None:
    schema_name: str = build_unique_schema_name(prefix=test_case.schema_prefix)
    config: dict[str, object] = build_sqlserver_config()
    escaped_schema_name: str = schema_name.replace("'", "''")
    try:
        ensure_sqlserver_schema_ready(schema_name=schema_name, config=config)
        assert_dbt_profile_lifecycle(
            tmp_path=tmp_path,
            profiles_yml=(
                "analytics:\n"
                "  target: dev\n"
                "  outputs:\n"
                "    dev:\n"
                "      type: sqlserver\n"
                "      driver: ODBC Driver 18 for SQL Server\n"
                f"      server: {config['host']}\n"
                f"      port: {config['port']}\n"
                f"      database: {config['database']}\n"
                f"      user: {config['user']}\n"
                f"      password: {config['password']}\n"
                f"      schema: {schema_name}\n"
                "      trust_cert: true\n"
            ),
            env=None,
            fetch_rows=lambda sql: fetch_sqlserver_rows(config=config, sql=sql),
            no_profile_tables_exist=lambda: (
                fetch_sqlserver_rows(
                    config=config,
                    sql=(
                        "SELECT t.name FROM sys.tables t "
                        "JOIN sys.schemas s ON t.schema_id = s.schema_id "
                        f"WHERE s.name = '{escaped_schema_name}' "
                        "AND t.name IN ('dbt_orders', 'downstream_orders') ORDER BY t.name"
                    ),
                )
                == ()
            ),
            dbt_orders_sql=(
                f"SELECT order_id FROM {relation_name(schema_name=schema_name, name='dbt_orders')} "
                "ORDER BY order_id"
            ),
            downstream_orders_sql=(
                "SELECT order_id FROM "
                f"{relation_name(schema_name=schema_name, name='downstream_orders')} "
                "ORDER BY order_id"
            ),
            expected_toml_fragments=test_case.expected_toml_fragments,
            unexpected_toml_fragments=(str(config["password"]),),
        )
    finally:
        cleanup_sqlserver_schema(schema_name=schema_name, config=config)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerBuildE2ETestCase(
            description="waffle shop full build succeeds on SQL Server",
            command=("--no-color", "build", "--concurrency", "4"),
            expected_table_name="fact_orders",
            expected_row_count=10,
            expected_stdout_fragments=("Execution", "OK"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_waffle_shop_when_running_full_build_on_sqlserver_then_expected_table_exists(
    tmp_path: Path,
    test_case: SqlServerBuildE2ETestCase,
) -> None:
    config: dict[str, object] = build_sqlserver_config()
    project_dir: Path
    schema_name: str
    project_dir, schema_name = prepare_sqlserver_waffle_shop(tmp_path=tmp_path, config=config)
    ensure_sqlserver_schema_ready(schema_name=schema_name, config=config)

    try:
        first_result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )
        cursor_type_rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            sql=(
                "SELECT data_type FROM information_schema.columns "
                f"WHERE table_schema = '{schema_name}' AND table_name = 'raw_orders' "
                "AND column_name = 'ordered_at'"
            ),
            config=config,
        )
        second_result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert cursor_type_rows == (("datetime",),)
        for result in (first_result, second_result):
            assert result.returncode == test_case.expected_return_code, (
                result.stdout + result.stderr
            )
            for fragment in test_case.expected_stdout_fragments:
                assert fragment in result.stdout
        rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            sql=(
                "SELECT COUNT(*) FROM "
                f"{relation_name(schema_name=schema_name, name=test_case.expected_table_name)}"
            ),
            config=config,
        )
        assert int(str(rows[0][0])) == test_case.expected_row_count
        source_rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            sql=(
                f"SELECT COUNT(*) FROM {relation_name(schema_name=schema_name, name='raw_orders')}"
            ),
            config=config,
        )
        assert int(str(source_rows[0][0])) == test_case.expected_row_count
    finally:
        cleanup_sqlserver_schema(schema_name=schema_name, config=config)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlServerSourceLoaderE2ETestCase(
            description="source loader build writes and reads SQL Server rows",
            expected_rows=(("7", "loaded-dev"),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_source_loader_project_when_building_on_sqlserver_then_model_reads_loaded_rows(
    tmp_path: Path,
    test_case: SqlServerSourceLoaderE2ETestCase,
) -> None:
    config: dict[str, object] = build_sqlserver_config()
    schema_name: str = build_unique_schema_name(prefix="sqb_e2e_loader")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="sqlserver_source_loader",
        repo_files={
            "sqlbuild_project.toml": build_sqlserver_project_toml(
                project_name="sqlserver_source_loader",
                schema_name=schema_name,
                config=config,
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n    description: Test source raw_orders.\n"
                "    managed: true\n"
                "    write_strategy: table\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
                "      - name: status\n"
                "        type: NVARCHAR(100)\n"
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
    ensure_sqlserver_schema_ready(schema_name=schema_name, config=config)

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build", "--select", "stg_orders"),
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
            config=config,
            sql=(
                "SELECT order_id, status FROM "
                f"{relation_name(schema_name=schema_name, name='stg_orders')} "
                "ORDER BY order_id"
            ),
        )
        assert stringify_warehouse_rows(rows) == test_case.expected_rows
    finally:
        cleanup_sqlserver_schema(schema_name=schema_name, config=config)
