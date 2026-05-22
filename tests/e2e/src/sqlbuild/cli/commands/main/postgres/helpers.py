"""Helpers for Postgres CLI e2e tests."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlbuild.integrations.postgres.client import PostgresAdapter
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_source_loader_strategies,
    prepare_waffle_shop,
    stringify_warehouse_rows,
)


def build_unique_schema_name(*, prefix: str) -> str:
    suffix: str = uuid.uuid4().hex[:10]
    return f"{prefix}_{suffix}"


def build_postgres_project_toml(
    *,
    project_name: str,
    schema_name: str,
    config: dict[str, object],
) -> str:
    return (
        f'name = "{project_name}"\n'
        'adapter = "postgres"\n'
        'default_environment = "dev"\n\n'
        "[connection]\n"
        f'host = "{config["host"]}"\n'
        f"port = {config['port']}\n"
        f'dbname = "{config["dbname"]}"\n'
        f'user = "{config["user"]}"\n'
        f'password = "{config["password"]}"\n\n'
        "[environments.dev]\n"
        f'schema = "{schema_name}"\n\n'
        "[defaults]\n"
        'materialized = "table"\n'
    )


def build_postgres_source_deferral_project_toml(
    *, project_name: str, dev_schema_name: str, prod_schema_name: str, config: dict[str, object]
) -> str:
    return (
        f'name = "{project_name}"\n'
        'adapter = "postgres"\n'
        'default_environment = "dev"\n\n'
        "[connection]\n"
        f'host = "{config["host"]}"\n'
        f"port = {config['port']}\n"
        f'dbname = "{config["dbname"]}"\n'
        f'user = "{config["user"]}"\n'
        f'password = "{config["password"]}"\n\n'
        "[environments.dev]\n"
        f'schema = "{dev_schema_name}"\n'
        'defer_sources_to = "prod"\n\n'
        "[environments.prod]\n"
        f'schema = "{prod_schema_name}"\n\n'
        "[defaults]\n"
        'materialized = "table"\n'
    )


def ensure_postgres_schema_ready(*, schema_name: str, config: dict[str, object]) -> None:
    adapter: PostgresAdapter = PostgresAdapter()
    connection: Any = adapter.connect(config)
    try:
        adapter.execute(connection, f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
    finally:
        adapter.close(connection)


def cleanup_postgres_schema(*, schema_name: str, config: dict[str, object]) -> None:
    adapter: PostgresAdapter = PostgresAdapter()
    connection: Any = adapter.connect(config)
    try:
        adapter.execute(connection, f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")
    finally:
        adapter.close(connection)


def fetch_postgres_rows(*, sql: str, config: dict[str, object]) -> tuple[tuple[object, ...], ...]:
    adapter: PostgresAdapter = PostgresAdapter()
    connection: Any = adapter.connect(config)
    try:
        cursor: Any = adapter.execute(connection, sql)
        return tuple(tuple(row) for row in cursor.fetchall())
    finally:
        adapter.close(connection)


def execute_postgres_sql(*, sql: str, config: dict[str, object]) -> None:
    adapter: PostgresAdapter = PostgresAdapter()
    connection: Any = adapter.connect(config)
    try:
        adapter.execute(connection, sql)
    finally:
        adapter.close(connection)


def relation_name(*, schema_name: str, name: str) -> str:
    return f"{schema_name}.{name}"


def postgres_relation_row_count(*, schema_name: str, name: str, config: dict[str, object]) -> int:
    rows: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
        sql=f"SELECT COUNT(*) FROM {relation_name(schema_name=schema_name, name=name)}",
        config=config,
    )
    return int(str(rows[0][0]))


def prepare_postgres_diff_project(
    *, tmp_path: Path, config: dict[str, object]
) -> tuple[Path, str, str]:
    prod_schema: str = build_unique_schema_name(prefix="sqb_diff_prod")
    dev_schema: str = build_unique_schema_name(prefix="sqb_diff_dev")
    project_dir: Path = tmp_path / "postgres_diff_project"
    project_dir.mkdir(parents=True, exist_ok=True)
    project_contents: str = (
        'name = "postgres_diff_project"\n'
        'adapter = "postgres"\n'
        'default_environment = "dev"\n\n'
        "[connection]\n"
        f'host = "{config["host"]}"\n'
        f"port = {config['port']}\n"
        f'dbname = "{config["dbname"]}"\n'
        f'user = "{config["user"]}"\n'
        f'password = "{config["password"]}"\n\n'
        "[environments.dev]\n"
        f'schema = "{dev_schema}"\n\n'
        "[environments.dev.clone]\n"
        "allow_as_source = true\n"
        "allow_as_target = true\n\n"
        "[environments.prod]\n"
        f'schema = "{prod_schema}"\n\n'
        "[environments.prod.clone]\n"
        "allow_as_source = true\n"
        "allow_as_target = false\n\n"
        "[defaults]\n"
        'materialized = "table"\n'
    )
    (project_dir / "sqlbuild_project.toml").write_text(project_contents, encoding="utf-8")
    models_dir: Path = project_dir / "models" / "staging"
    models_dir.mkdir(parents=True, exist_ok=True)
    (models_dir / "stg_orders.sql").write_text(
        "MODEL (materialized table, unique_key [order_id]);\n\n"
        "SELECT * FROM ("
        "SELECT 1 AS order_id, 1 AS customer_id, 100 AS amount_cents UNION ALL "
        "SELECT 2 AS order_id, 2 AS customer_id, 200 AS amount_cents"
        ")",
        encoding="utf-8",
    )
    return project_dir, prod_schema, dev_schema


def assert_current_postgres_snapshot_rows_from_case(
    *,
    schema_name: str,
    config: dict[str, object],
    expected_rows: tuple[tuple[object, ...], ...],
) -> None:
    assert_current_postgres_snapshot_rows(
        schema_name=schema_name,
        config=config,
        expected_rows=expected_rows,
    )


def assert_current_postgres_snapshot_rows(
    *,
    schema_name: str,
    config: dict[str, object],
    expected_rows: tuple[tuple[object, ...], ...],
) -> None:
    rows: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
        sql=(
            "SELECT customer_id, region_id, plan, "
            "CAST(effective_from AS DATE), CAST(effective_to AS DATE) "
            f"FROM {relation_name(schema_name=schema_name, name='current_customer_snapshot')} "
            "ORDER BY customer_id, region_id, effective_from"
        ),
        config=config,
    )
    assert stringify_warehouse_rows(rows) == expected_rows


def assert_postgres_snapshot_matrix_rows(
    *,
    schema_name: str,
    config: dict[str, object],
    expected_current_rows: tuple[tuple[object, ...], ...],
    expected_historical_timestamp_rows: tuple[tuple[object, ...], ...],
    expected_historical_check_rows: tuple[tuple[object, ...], ...],
) -> None:
    assert_current_postgres_snapshot_rows(
        schema_name=schema_name,
        config=config,
        expected_rows=expected_current_rows,
    )
    historical_timestamp_rows: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
        sql=(
            "SELECT customer_id, plan, CAST(valid_from AS DATE), CAST(valid_to AS DATE) "
            f"FROM {relation_name(schema_name=schema_name, name='historical_customer_snapshot')} "
            "ORDER BY customer_id, valid_from"
        ),
        config=config,
    )
    historical_check_rows: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
        sql=(
            "SELECT customer_id, status, CAST(valid_from AS DATE), CAST(valid_to AS DATE) "
            f"FROM {relation_name(schema_name=schema_name, name='historical_membership_snapshot')} "
            "ORDER BY customer_id, valid_from"
        ),
        config=config,
    )
    assert stringify_warehouse_rows(historical_timestamp_rows) == expected_historical_timestamp_rows
    assert stringify_warehouse_rows(historical_check_rows) == expected_historical_check_rows


def assert_postgres_snapshot_apply_rows(
    *,
    schema_name: str,
    config: dict[str, object],
    expected_current_check_rows: tuple[tuple[object, ...], ...],
    expected_current_delete_rows: tuple[tuple[object, ...], ...],
    expected_historical_timestamp_rows: tuple[tuple[object, ...], ...],
    expected_historical_check_rows: tuple[tuple[object, ...], ...],
) -> None:
    current_check_rows: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
        sql=(
            "SELECT customer_id, status, valid_to IS NULL "
            f"FROM {relation_name(schema_name=schema_name, name='current_check_snapshot')} "
            "ORDER BY customer_id, status, valid_to IS NULL"
        ),
        config=config,
    )
    current_delete_rows: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
        sql=(
            "SELECT customer_id, plan, valid_to IS NULL "
            f"FROM {relation_name(schema_name=schema_name, name='current_delete_snapshot')} "
            "ORDER BY customer_id, plan, valid_to IS NULL"
        ),
        config=config,
    )
    historical_timestamp_rows: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
        sql=(
            "SELECT customer_id, plan, CAST(valid_from AS DATE), CAST(valid_to AS DATE) "
            f"FROM {relation_name(schema_name=schema_name, name='historical_timestamp_snapshot')} "
            "ORDER BY customer_id, valid_from"
        ),
        config=config,
    )
    historical_check_rows: tuple[tuple[object, ...], ...] = fetch_postgres_rows(
        sql=(
            "SELECT customer_id, status, CAST(valid_from AS DATE), CAST(valid_to AS DATE) "
            f"FROM {relation_name(schema_name=schema_name, name='historical_check_snapshot')} "
            "ORDER BY customer_id, valid_from"
        ),
        config=config,
    )
    assert stringify_warehouse_rows(current_check_rows) == expected_current_check_rows
    assert stringify_warehouse_rows(current_delete_rows) == expected_current_delete_rows
    assert stringify_warehouse_rows(historical_timestamp_rows) == expected_historical_timestamp_rows
    assert stringify_warehouse_rows(historical_check_rows) == expected_historical_check_rows


def prepare_postgres_waffle_shop(*, tmp_path: Path, config: dict[str, object]) -> tuple[Path, str]:
    """Copy waffle shop to tmp dir and wire it to a unique Postgres schema."""

    schema_name: str = build_unique_schema_name(prefix="sqb_waffle")
    project_dir: Path = prepare_waffle_shop(tmp_path)

    (project_dir / "functions" / "sql" / "customer_orders.sql").unlink(missing_ok=True)
    (project_dir / "functions" / "python" / "is_completed_order_py.py").unlink(missing_ok=True)
    (project_dir / "tests" / "unit" / "test_customer_orders_table_fn.sql").unlink(missing_ok=True)
    (project_dir / "models" / "marts" / "daily_order_partitioned.sql").unlink(missing_ok=True)
    (project_dir / "tests" / "unit" / "test_is_completed_order_udf.sql").unlink(missing_ok=True)
    is_completed_order_path: Path = project_dir / "functions" / "sql" / "is_completed_order.sql"
    is_completed_order_path.write_text(
        is_completed_order_path.read_text(encoding="utf-8")
        .replace("STRING", "TEXT")
        .replace("order_status = 'completed'", "SELECT order_status = 'completed'"),
        encoding="utf-8",
    )

    fact_orders_path: Path = project_dir / "models" / "marts" / "fact_orders.sql"
    fact_orders_path.write_text(
        fact_orders_path.read_text(encoding="utf-8").replace(
            '__udf("is_completed_order_py")(o.status) AS is_completed_order_py,',
            '__udf("is_completed_order")(o.status) AS is_completed_order_py,',
        ),
        encoding="utf-8",
    )
    project_file_path: Path = project_dir / "sqlbuild_project.toml"
    project_file_path.write_text(
        'name = "waffle_shop"\n'
        'adapter = "postgres"\n'
        'default_environment = "dev"\n\n'
        "[connection]\n"
        f'host = "{config["host"]}"\n'
        f"port = {config['port']}\n"
        f'dbname = "{config["dbname"]}"\n'
        f'user = "{config["user"]}"\n'
        f'password = "{config["password"]}"\n\n'
        "[settings]\n"
        'default_audit_severity = "warn"\n\n'
        "[defaults]\n"
        'materialized = "table"\n\n'
        "[environments.dev]\n"
        f'schema = "{schema_name}"\n\n'
        "[path_defaults.staging]\n"
        'materialized = "view"\n',
        encoding="utf-8",
    )
    return project_dir, schema_name


def prepare_postgres_source_loader_strategies(
    *, tmp_path: Path, config: dict[str, object]
) -> tuple[Path, str]:
    """Prepare source-loader strategy fixture wired to a unique Postgres schema."""

    schema_name: str = build_unique_schema_name(prefix="sqb_load")
    project_dir: Path = prepare_source_loader_strategies(
        tmp_path=tmp_path,
        project_toml=build_postgres_project_toml(
            project_name="source_loader_strategies",
            schema_name=schema_name,
            config=config,
        ),
    )
    return project_dir, schema_name
