"""Helpers for Databricks CLI e2e tests."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlbuild.adapters.databricks.client import DatabricksAdapter
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    assert_dbt_seeded_reuse_from_lifecycle,
    assert_dbt_snapshot_seeded_reuse_from_lifecycle,
    prepare_source_loader_strategies,
    prepare_waffle_shop,
    stringify_warehouse_rows,
)
from tests.integration.src.sqlbuild.adapters.databricks.helpers import (
    build_databricks_connection_config,
    build_unique_schema_name,
    fetch_rows,
    qualified_name,
)


def build_databricks_local_config(*, environment: str = "dev", schema_name: str) -> str:
    """Build a local config pointing the project at Databricks."""

    return (
        'adapter = "databricks"\n'
        f'target = "{environment}"\n\n'
        "[connection]\n"
        'server_hostname = "${ENV:SQB_TEST_DATABRICKS_SERVER_HOSTNAME}"\n'
        'http_path = "${ENV:SQB_TEST_DATABRICKS_HTTP_PATH}"\n'
        'token = "${ENV:SQB_TEST_DATABRICKS_TOKEN}"\n'
        'catalog = "${ENV:SQB_TEST_DATABRICKS_CATALOG}"\n'
        f'schema = "{schema_name}"\n'
    )


def build_databricks_project_toml(*, project_name: str, schema_name: str) -> str:
    """Build project TOML for an inline Databricks e2e project."""

    catalog_name: str = str(build_databricks_connection_config(schema=schema_name)["catalog"])
    return (
        f'name = "{project_name}"\n'
        'adapter = "databricks"\n'
        'default_target = "dev"\n\n'
        "[connection]\n"
        'server_hostname = "${ENV:SQB_TEST_DATABRICKS_SERVER_HOSTNAME}"\n'
        'http_path = "${ENV:SQB_TEST_DATABRICKS_HTTP_PATH}"\n'
        'token = "${ENV:SQB_TEST_DATABRICKS_TOKEN}"\n'
        'catalog = "${ENV:SQB_TEST_DATABRICKS_CATALOG}"\n\n'
        "[targets.dev]\n"
        f'database = "{catalog_name}"\n'
        f'schema = "{schema_name}"\n'
        'defer_sources_to = "dev"\n\n'
        "[defaults]\n"
        'materialized = "table"\n'
    )


def assert_databricks_seeded_reuse_case(
    *,
    tmp_path: Path,
    schema_prefix: str,
    expected_rows: tuple[tuple[object, ...], ...],
    snapshot: bool,
) -> None:
    schema_base: str = build_unique_schema_name(prefix=schema_prefix)
    dev_schema_name: str = f"{schema_base}_dev"
    prod_schema_name: str = f"{schema_base}_prod"
    config: dict[str, object] = build_databricks_connection_config(schema=dev_schema_name)
    catalog_name: str = str(config["catalog"])
    try:
        ensure_databricks_schema_ready(schema_name=dev_schema_name)
        ensure_databricks_schema_ready(schema_name=prod_schema_name)
        relation: str = "orders_snapshot" if snapshot else "fact_orders"
        current_filter: str = " WHERE dbt_valid_to IS NULL" if snapshot else ""
        profiles_yml: str = _databricks_reuse_profiles_yml(
            config=config,
            catalog_name=catalog_name,
            dev_schema_name=dev_schema_name,
            prod_schema_name=prod_schema_name,
        )
        project_toml: str = _databricks_reuse_project_toml(dev_schema_name=dev_schema_name)
        destination_rows_sql: str = (
            "SELECT order_id, amount FROM "
            f"{relation_name(schema_name=dev_schema_name, name=relation)}"
            f"{current_filter} ORDER BY order_id"
        )
        downstream_rows_sql: str = (
            "SELECT order_id, downstream_amount FROM "
            f"{relation_name(schema_name=dev_schema_name, name='downstream_orders')} "
            "ORDER BY order_id"
        )
        if snapshot:
            assert_dbt_snapshot_seeded_reuse_from_lifecycle(
                tmp_path=tmp_path,
                profiles_yml=profiles_yml,
                project_toml=project_toml,
                origin_snapshot_schema=prod_schema_name,
                destination_snapshot_schema=dev_schema_name,
                fetch_rows=lambda sql: fetch_databricks_rows(schema_name=dev_schema_name, sql=sql),
                destination_rows_sql=destination_rows_sql,
                downstream_rows_sql=downstream_rows_sql,
                expected_rows=expected_rows,
            )
        else:
            assert_dbt_seeded_reuse_from_lifecycle(
                tmp_path=tmp_path,
                profiles_yml=profiles_yml,
                project_toml=project_toml,
                fetch_rows=lambda sql: fetch_databricks_rows(schema_name=dev_schema_name, sql=sql),
                destination_rows_sql=destination_rows_sql,
                downstream_rows_sql=downstream_rows_sql,
                expected_rows=expected_rows,
            )
    finally:
        cleanup_databricks_schema(schema_name=dev_schema_name)
        cleanup_databricks_schema(schema_name=prod_schema_name)


def _databricks_reuse_profiles_yml(
    *, config: dict[str, object], catalog_name: str, dev_schema_name: str, prod_schema_name: str
) -> str:
    return (
        "analytics:\n"
        "  target: dev\n"
        "  outputs:\n"
        "    dev:\n"
        "      type: databricks\n"
        f"      host: {config['server_hostname']}\n"
        f"      http_path: {config['http_path']}\n"
        f"      token: {config['token']}\n"
        f"      catalog: {catalog_name}\n"
        f"      schema: {dev_schema_name}\n"
        "    prod:\n"
        "      type: databricks\n"
        f"      host: {config['server_hostname']}\n"
        f"      http_path: {config['http_path']}\n"
        f"      token: {config['token']}\n"
        f"      catalog: {catalog_name}\n"
        f"      schema: {prod_schema_name}\n"
    )


def _databricks_reuse_project_toml(*, dev_schema_name: str) -> str:
    return (
        build_databricks_project_toml(
            project_name="databricks_dbt_reuse_from",
            schema_name=dev_schema_name,
        )
        + "\n[dbt]\n"
        + 'project_dir = "../dbt_project"\n'
        + 'profiles_dir = "../profiles"\n'
        + 'target_path = "../dbt_project/target"\n'
        + "[dbt.reuse_from]\n"
        + 'git_ref = "prod"\n'
        + 'generate_schema_name_override = "dbt/macros/prod_generate_schema_name.sql"\n'
    )


def build_databricks_virtual_project_toml(
    *, project_name: str, schema_name: str, unsuffixed_virtual_env: str | None = None
) -> str:
    catalog_name: str = str(build_databricks_connection_config(schema=schema_name)["catalog"])
    unsuffixed_line: str = (
        f'unsuffixed_virtual_env = "{unsuffixed_virtual_env}"\n'
        if unsuffixed_virtual_env is not None
        else ""
    )
    return (
        f'name = "{project_name}"\n'
        'adapter = "databricks"\n'
        'default_target = "dev"\n\n'
        "[settings]\n"
        "virtual_environments = true\n"
        "\n"
        "[connection]\n"
        'server_hostname = "${ENV:SQB_TEST_DATABRICKS_SERVER_HOSTNAME}"\n'
        'http_path = "${ENV:SQB_TEST_DATABRICKS_HTTP_PATH}"\n'
        'token = "${ENV:SQB_TEST_DATABRICKS_TOKEN}"\n'
        'catalog = "${ENV:SQB_TEST_DATABRICKS_CATALOG}"\n\n'
        "[targets.dev]\n"
        f'database = "{catalog_name}"\n'
        f'schema = "{schema_name}"\n\n'
        "[targets.dev.state]\n"
        'backend = "duckdb"\n'
        'schema = "sqlbuild_state"\n'
        f"{unsuffixed_line}\n"
        "[targets.dev.state.connection]\n"
        'database = "state.duckdb"\n'
    )


def prepare_databricks_waffle_shop(*, tmp_path: Path) -> tuple[Path, str]:
    """Prepare a Waffle Shop project wired to a unique Databricks schema."""

    project_dir: Path = prepare_waffle_shop(tmp_path)
    schema_name: str = build_unique_schema_name(prefix="sqlbuild_e2e")
    catalog_name: str = str(build_databricks_connection_config(schema=schema_name)["catalog"])
    project_file_path: Path = project_dir / "sqlbuild_project.toml"
    project_contents: str = (
        'name = "waffle_shop"\n'
        'adapter = "databricks"\n'
        'default_target = "dev"\n\n'
        "[connection]\n"
        'server_hostname = "${ENV:SQB_TEST_DATABRICKS_SERVER_HOSTNAME}"\n'
        'http_path = "${ENV:SQB_TEST_DATABRICKS_HTTP_PATH}"\n'
        'token = "${ENV:SQB_TEST_DATABRICKS_TOKEN}"\n'
        'catalog = "${ENV:SQB_TEST_DATABRICKS_CATALOG}"\n'
        f'schema = "{schema_name}"\n\n'
        "[settings]\n"
        'default_audit_severity = "warn"\n\n'
        "[defaults]\n"
        'materialized = "table"\n\n'
        "[targets.dev]\n"
        f'database = "{catalog_name}"\n'
        f'schema = "{schema_name}"\n'
        'defer_sources_to = "dev"\n\n'
        "[targets.prod]\n"
        f'database = "{catalog_name}"\n'
        f'schema = "{schema_name}"\n\n'
        "[path_defaults.staging]\n"
        'materialized = "view"\n'
    )
    project_file_path.write_text(project_contents, encoding="utf-8")
    (project_dir / "sqlbuild_local.toml").write_text(
        build_databricks_local_config(schema_name=schema_name),
        encoding="utf-8",
    )
    return project_dir, schema_name


def prepare_databricks_source_loader_strategies(*, tmp_path: Path) -> tuple[Path, str]:
    """Prepare source-loader strategy fixture wired to a unique Databricks schema."""

    schema_name: str = build_unique_schema_name(prefix="sqlbuild_e2e_load")
    project_dir: Path = prepare_source_loader_strategies(
        tmp_path=tmp_path,
        project_toml=build_databricks_project_toml(
            project_name="source_loader_strategies",
            schema_name=schema_name,
        ),
    )
    return project_dir, schema_name


@contextmanager
def databricks_e2e_timing(label: str) -> Iterator[None]:
    """Print opt-in coarse timing for slow real-warehouse e2e phases."""

    if os.environ.get("SQB_E2E_TIMING") != "1":
        yield
        return
    start: float = time.perf_counter()
    try:
        yield
    finally:
        elapsed: float = time.perf_counter() - start
        print(f"[sqb-e2e-timing] {label}: {elapsed:.2f}s", flush=True)


def ensure_databricks_schema_ready(*, schema_name: str) -> None:
    """Precreate schema so sqb query can activate the configured session schema."""

    adapter: DatabricksAdapter = DatabricksAdapter()
    config: dict[str, object] = build_databricks_connection_config(schema=schema_name)
    catalog_name: str = str(config["catalog"])
    connection: Any = adapter.connect(config)
    try:
        adapter.execute(connection, f"CREATE SCHEMA IF NOT EXISTS `{catalog_name}`.`{schema_name}`")
    finally:
        adapter.close(connection)


def cleanup_databricks_schema(*, schema_name: str) -> None:
    """Drop the generated Databricks schema after a test completes."""

    adapter: DatabricksAdapter = DatabricksAdapter()
    config: dict[str, object] = build_databricks_connection_config(schema=schema_name)
    catalog_name: str = str(config["catalog"])
    connection: Any = adapter.connect(config)
    try:
        adapter.execute(
            connection, f"DROP SCHEMA IF EXISTS `{catalog_name}`.`{schema_name}` CASCADE"
        )
    finally:
        adapter.close(connection)


def fetch_databricks_rows(*, schema_name: str, sql: str) -> tuple[tuple[object, ...], ...]:
    """Fetch rows from Databricks using the configured test credentials."""

    adapter: DatabricksAdapter = DatabricksAdapter()
    config: dict[str, object] = build_databricks_connection_config(schema=schema_name)
    connection: Any = adapter.connect(config)
    try:
        return fetch_rows(adapter=adapter, connection=connection, sql=sql)
    finally:
        adapter.close(connection)


def list_databricks_scenario_relation_names(*, schema_name: str) -> tuple[str, ...]:
    """Return scenario artifact relation names in a Databricks schema."""

    catalog_name: str = str(build_databricks_connection_config(schema=schema_name)["catalog"])
    rows: tuple[tuple[object, ...], ...] = fetch_databricks_rows(
        schema_name=schema_name,
        sql=(
            f"SELECT table_name FROM `{catalog_name}`.information_schema.tables "
            f"WHERE table_schema = '{schema_name}' "
            "AND table_name LIKE '__sqb_%' ORDER BY table_name"
        ),
    )
    return tuple(str(row[0]) for row in rows)


def databricks_relation_row_count(*, schema_name: str, relation: str) -> int:
    """Return row count for one Databricks relation."""

    rows: tuple[tuple[object, ...], ...] = fetch_databricks_rows(
        schema_name=schema_name,
        sql=f"SELECT COUNT(*) FROM {relation_name(schema_name=schema_name, name=relation)}",
    )
    return int(str(rows[0][0]))


def relation_name(*, schema_name: str, name: str) -> str:
    """Return a fully qualified relation name for a Databricks e2e schema."""

    catalog_name: str = str(build_databricks_connection_config(schema=schema_name)["catalog"])
    return qualified_name(catalog=catalog_name, schema=schema_name, name=name)


def prepare_databricks_query_source(*, schema_name: str) -> str:
    """Create a simple source table used by query CLI tests."""

    table_name: str = relation_name(schema_name=schema_name, name="query_source")
    execute_databricks_sql(
        schema_name=schema_name,
        sql=(
            f"CREATE OR REPLACE TABLE {table_name} AS "
            "SELECT 1 AS id, 'alice' AS name UNION ALL SELECT 2 AS id, 'bob' AS name"
        ),
    )
    return table_name


def prepare_databricks_diff_project(*, tmp_path: Path) -> tuple[Path, str, str]:
    """Prepare a Databricks-backed diff project with explicit prod/dev target schemas."""

    project_dir: Path = tmp_path / "databricks_diff_project"
    prod_schema: str = build_unique_schema_name(prefix="sqlbuild_diff_prod")
    dev_schema: str = build_unique_schema_name(prefix="sqlbuild_diff_dev")
    catalog_name: str = str(build_databricks_connection_config(schema=dev_schema)["catalog"])
    project_contents: str = (
        'name = "databricks_diff_project"\n'
        'adapter = "databricks"\n'
        'default_target = "dev"\n\n'
        "[connection]\n"
        'server_hostname = "${ENV:SQB_TEST_DATABRICKS_SERVER_HOSTNAME}"\n'
        'http_path = "${ENV:SQB_TEST_DATABRICKS_HTTP_PATH}"\n'
        'token = "${ENV:SQB_TEST_DATABRICKS_TOKEN}"\n'
        'catalog = "${ENV:SQB_TEST_DATABRICKS_CATALOG}"\n\n'
        "[targets.dev]\n"
        f'database = "{catalog_name}"\n'
        f'schema = "{dev_schema}"\n\n'
        "[targets.dev.clone]\n"
        "allow_as_clone_origin = true\n"
        "allow_as_clone_destination = true\n\n"
        "[targets.prod]\n"
        f'database = "{catalog_name}"\n'
        f'schema = "{prod_schema}"\n\n'
        "[targets.prod.clone]\n"
        "allow_as_clone_origin = true\n"
        "allow_as_clone_destination = false\n\n"
        "[defaults]\n"
        'materialized = "table"\n'
    )
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "sqlbuild_project.toml").write_text(project_contents, encoding="utf-8")
    (project_dir / "sqlbuild_local.toml").write_text(
        build_databricks_local_config(schema_name=dev_schema),
        encoding="utf-8",
    )
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


def execute_databricks_sql(*, schema_name: str, sql: str) -> None:
    """Execute mutating SQL against a Databricks schema."""

    adapter: DatabricksAdapter = DatabricksAdapter()
    config: dict[str, object] = build_databricks_connection_config(schema=schema_name)
    connection: Any = adapter.connect(config)
    try:
        ensure_databricks_schema_ready(schema_name=schema_name)
        adapter.execute(connection, sql)
    finally:
        adapter.close(connection)


def write_local_environment_override(
    *, project_dir: Path, environment: str, schema_name: str
) -> None:
    """Write a local environment override for Databricks CLI e2e commands."""

    (project_dir / "sqlbuild_local.toml").write_text(
        build_databricks_local_config(environment=environment, schema_name=schema_name),
        encoding="utf-8",
    )


def assert_current_databricks_snapshot_rows(
    *, schema_name: str, expected_rows: tuple[tuple[object, ...], ...]
) -> None:
    """Assert current snapshot rows for Databricks real-warehouse e2e tests."""

    rows: tuple[tuple[object, ...], ...] = fetch_databricks_rows(
        schema_name=schema_name,
        sql=(
            "SELECT customer_id, region_id, plan, CAST(effective_from AS DATE), "
            "CAST(effective_to AS DATE) "
            f"FROM {relation_name(schema_name=schema_name, name='current_customer_snapshot')} "
            "ORDER BY customer_id, region_id, effective_from"
        ),
    )
    assert stringify_warehouse_rows(rows) == expected_rows


def assert_databricks_snapshot_matrix_rows(
    *,
    schema_name: str,
    expected_current_rows: tuple[tuple[object, ...], ...],
    expected_historical_timestamp_rows: tuple[tuple[object, ...], ...],
    expected_historical_check_rows: tuple[tuple[object, ...], ...],
) -> None:
    """Assert all compact snapshot matrix rows for Databricks."""

    assert_current_databricks_snapshot_rows(
        schema_name=schema_name,
        expected_rows=expected_current_rows,
    )
    historical_timestamp_rows: tuple[tuple[object, ...], ...] = fetch_databricks_rows(
        schema_name=schema_name,
        sql=(
            "SELECT customer_id, plan, CAST(valid_from AS DATE), CAST(valid_to AS DATE) "
            f"FROM {relation_name(schema_name=schema_name, name='historical_customer_snapshot')} "
            "ORDER BY customer_id, valid_from"
        ),
    )
    historical_check_rows: tuple[tuple[object, ...], ...] = fetch_databricks_rows(
        schema_name=schema_name,
        sql=(
            "SELECT customer_id, status, CAST(valid_from AS DATE), CAST(valid_to AS DATE) "
            f"FROM {relation_name(schema_name=schema_name, name='historical_membership_snapshot')} "
            "ORDER BY customer_id, valid_from"
        ),
    )
    actual_historical_timestamp_rows: tuple[tuple[object, ...], ...] = stringify_warehouse_rows(
        historical_timestamp_rows
    )
    actual_historical_check_rows: tuple[tuple[object, ...], ...] = stringify_warehouse_rows(
        historical_check_rows
    )
    assert actual_historical_timestamp_rows == expected_historical_timestamp_rows, (
        actual_historical_timestamp_rows
    )
    assert actual_historical_check_rows == expected_historical_check_rows, (
        actual_historical_check_rows
    )


def assert_databricks_snapshot_apply_rows(
    *,
    schema_name: str,
    expected_current_check_rows: tuple[tuple[object, ...], ...],
    expected_current_delete_rows: tuple[tuple[object, ...], ...],
    expected_historical_timestamp_rows: tuple[tuple[object, ...], ...],
    expected_historical_check_rows: tuple[tuple[object, ...], ...],
) -> None:
    """Assert existing-target snapshot apply rows for Databricks."""

    current_check_rows: tuple[tuple[object, ...], ...] = fetch_databricks_rows(
        schema_name=schema_name,
        sql=(
            "SELECT customer_id, status, valid_to IS NULL "
            f"FROM {relation_name(schema_name=schema_name, name='current_check_snapshot')} "
            "ORDER BY customer_id, status, valid_to IS NULL"
        ),
    )
    current_delete_rows: tuple[tuple[object, ...], ...] = fetch_databricks_rows(
        schema_name=schema_name,
        sql=(
            "SELECT customer_id, plan, valid_to IS NULL "
            f"FROM {relation_name(schema_name=schema_name, name='current_delete_snapshot')} "
            "ORDER BY customer_id, plan, valid_to IS NULL"
        ),
    )
    historical_timestamp_rows: tuple[tuple[object, ...], ...] = fetch_databricks_rows(
        schema_name=schema_name,
        sql=(
            "SELECT customer_id, plan, CAST(valid_from AS DATE), CAST(valid_to AS DATE) "
            f"FROM {relation_name(schema_name=schema_name, name='historical_timestamp_snapshot')} "
            "ORDER BY customer_id, valid_from"
        ),
    )
    historical_check_rows: tuple[tuple[object, ...], ...] = fetch_databricks_rows(
        schema_name=schema_name,
        sql=(
            "SELECT customer_id, status, CAST(valid_from AS DATE), CAST(valid_to AS DATE) "
            f"FROM {relation_name(schema_name=schema_name, name='historical_check_snapshot')} "
            "ORDER BY customer_id, valid_from"
        ),
    )
    assert stringify_warehouse_rows(current_check_rows) == expected_current_check_rows
    assert stringify_warehouse_rows(current_delete_rows) == expected_current_delete_rows
    assert stringify_warehouse_rows(historical_timestamp_rows) == expected_historical_timestamp_rows
    assert stringify_warehouse_rows(historical_check_rows) == expected_historical_check_rows
