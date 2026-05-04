"""Helpers for Databricks CLI e2e tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.integrations.databricks.client import DatabricksAdapter
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import prepare_waffle_shop
from tests.integration.src.sqlbuild.integrations.databricks.helpers import (
    build_databricks_connection_config,
    build_unique_schema_name,
    fetch_rows,
    qualified_name,
)


def build_databricks_local_config(*, environment: str = "dev", schema_name: str) -> str:
    """Build a local config pointing the project at Databricks."""

    return (
        "adapter: databricks\n"
        f"environment: {environment}\n"
        "connection:\n"
        "  server_hostname: ${ENV:SQB_TEST_DATABRICKS_SERVER_HOSTNAME}\n"
        "  http_path: ${ENV:SQB_TEST_DATABRICKS_HTTP_PATH}\n"
        "  token: ${ENV:SQB_TEST_DATABRICKS_TOKEN}\n"
        "  catalog: ${ENV:SQB_TEST_DATABRICKS_CATALOG}\n"
        f"  schema: {schema_name}\n"
    )


def prepare_databricks_waffle_shop(*, tmp_path: Path) -> tuple[Path, str]:
    """Prepare a Waffle Shop project wired to a unique Databricks schema."""

    project_dir: Path = prepare_waffle_shop(tmp_path)
    schema_name: str = build_unique_schema_name(prefix="sqlbuild_e2e")
    catalog_name: str = str(build_databricks_connection_config(schema=schema_name)["catalog"])
    project_file_path: Path = project_dir / "sqlbuild_project.yml"
    project_contents: str = (
        "name: waffle_shop\n"
        "adapter: databricks\n\n"
        "default_environment: dev\n\n"
        "connection:\n"
        "  server_hostname: ${ENV:SQB_TEST_DATABRICKS_SERVER_HOSTNAME}\n"
        "  http_path: ${ENV:SQB_TEST_DATABRICKS_HTTP_PATH}\n"
        "  token: ${ENV:SQB_TEST_DATABRICKS_TOKEN}\n"
        "  catalog: ${ENV:SQB_TEST_DATABRICKS_CATALOG}\n"
        f"  schema: {schema_name}\n\n"
        "settings:\n"
        "  default_audit_severity: warn\n\n"
        "defaults:\n"
        "  materialized: table\n\n"
        "environments:\n"
        f"  dev:\n    database: {catalog_name}\n    schema: {schema_name}\n"
        f"  prod:\n    database: {catalog_name}\n    schema: {schema_name}\n\n"
        "path_defaults:\n"
        "  staging:\n"
        "    materialized: view\n"
    )
    project_file_path.write_text(project_contents, encoding="utf-8")
    (project_dir / "sqlbuild_local.yml").write_text(
        build_databricks_local_config(schema_name=schema_name),
        encoding="utf-8",
    )
    return project_dir, schema_name


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
        "name: databricks_diff_project\n"
        "adapter: databricks\n\n"
        "default_environment: dev\n\n"
        "connection:\n"
        "  server_hostname: ${ENV:SQB_TEST_DATABRICKS_SERVER_HOSTNAME}\n"
        "  http_path: ${ENV:SQB_TEST_DATABRICKS_HTTP_PATH}\n"
        "  token: ${ENV:SQB_TEST_DATABRICKS_TOKEN}\n"
        "  catalog: ${ENV:SQB_TEST_DATABRICKS_CATALOG}\n\n"
        "environments:\n"
        f"  dev:\n    database: {catalog_name}\n    schema: {dev_schema}\n"
        f"  prod:\n    database: {catalog_name}\n    schema: {prod_schema}\n\n"
        "defaults:\n"
        "  materialized: table\n"
    )
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "sqlbuild_project.yml").write_text(project_contents, encoding="utf-8")
    (project_dir / "sqlbuild_local.yml").write_text(
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

    (project_dir / "sqlbuild_local.yml").write_text(
        build_databricks_local_config(environment=environment, schema_name=schema_name),
        encoding="utf-8",
    )
