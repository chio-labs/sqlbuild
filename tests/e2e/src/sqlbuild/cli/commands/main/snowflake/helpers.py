"""Helpers for Snowflake CLI e2e tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.integrations.snowflake.client import SnowflakeAdapter
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import prepare_waffle_shop
from tests.integration.src.sqlbuild.integrations.snowflake.helpers import (
    build_snowflake_connection_config,
    build_unique_schema_name,
    create_schema_if_missing,
    fetch_rows,
    qualified_name,
)


def build_snowflake_local_config(*, schema_name: str) -> str:
    """Build a local config pointing the example project at Snowflake."""

    return (
        "adapter: snowflake\n"
        "connection:\n"
        "  account: ${ENV:SQB_TEST_SNOWFLAKE_ACCOUNT}\n"
        "  user: ${ENV:SQB_TEST_SNOWFLAKE_USER}\n"
        "  authenticator: ${ENV:SQB_TEST_SNOWFLAKE_AUTHENTICATOR}\n"
        "  token: ${ENV:SQB_TEST_SNOWFLAKE_PAT}\n"
        "  role: ${ENV:SQB_TEST_SNOWFLAKE_ROLE}\n"
        "  warehouse: ${ENV:SQB_TEST_SNOWFLAKE_WAREHOUSE}\n"
        "  database: ${ENV:SQB_TEST_SNOWFLAKE_DATABASE}\n"
        f"  schema: {schema_name}\n"
    )


def prepare_snowflake_waffle_shop(*, tmp_path: Path) -> tuple[Path, str]:
    """Prepare a Waffle Shop project wired to a unique Snowflake schema."""

    project_dir: Path = prepare_waffle_shop(tmp_path)
    schema_name: str = build_unique_schema_name(prefix="sqlbuild_e2e")
    database_name: str = str(build_snowflake_connection_config(schema=schema_name)["database"])
    project_file_path: Path = project_dir / "sqlbuild_project.yml"
    project_contents: str = (
        "name: waffle_shop\n"
        "adapter: duckdb\n\n"
        "default_environment: dev\n\n"
        "connection:\n"
        "  database: waffle_shop.duckdb\n\n"
        "settings:\n"
        "  default_audit_severity: warn\n\n"
        "defaults:\n"
        "  materialized: table\n\n"
        "environments:\n"
        f"  dev:\n    database: {database_name}\n    schema: {schema_name}\n"
        f"  prod:\n    database: {database_name}\n    schema: {schema_name}\n\n"
        "path_defaults:\n"
        "  staging:\n"
        "    materialized: view\n"
    )
    project_file_path.write_text(project_contents, encoding="utf-8")
    (project_dir / "sqlbuild_local.yml").write_text(
        build_snowflake_local_config(schema_name=schema_name),
        encoding="utf-8",
    )
    return project_dir, schema_name


def ensure_query_schema_ready(*, schema_name: str) -> None:
    """Precreate schema so sqb query can activate the configured session schema."""

    create_schema_if_missing(schema=schema_name)


def cleanup_snowflake_schema(*, schema_name: str) -> None:
    """Drop the generated Snowflake schema after a test completes."""

    adapter: SnowflakeAdapter = SnowflakeAdapter()
    config: dict[str, object] = build_snowflake_connection_config(schema=schema_name)
    database_name: str = str(config["database"])
    connection: Any = adapter.connect(config)
    try:
        adapter.execute(
            connection,
            f"DROP SCHEMA IF EXISTS {database_name}.{schema_name} CASCADE",
        )
    finally:
        adapter.close(connection)


def fetch_snowflake_rows(*, schema_name: str, sql: str) -> tuple[tuple[object, ...], ...]:
    """Fetch rows from Snowflake using the configured test credentials."""

    adapter: SnowflakeAdapter = SnowflakeAdapter()
    config: dict[str, object] = build_snowflake_connection_config(schema=schema_name)
    connection: Any = adapter.connect(config)
    try:
        return fetch_rows(adapter=adapter, connection=connection, sql=sql)
    finally:
        adapter.close(connection)


def relation_name(*, schema_name: str, name: str) -> str:
    """Return a fully qualified relation name for a Snowflake e2e schema."""

    database_name: str = str(build_snowflake_connection_config(schema=schema_name)["database"])
    return qualified_name(database=database_name, schema=schema_name, name=name)


def prepare_snowflake_diff_project(*, tmp_path: Path) -> tuple[Path, str, str]:
    """Prepare a Snowflake-backed diff project with explicit prod/dev target schemas."""

    project_dir: Path = tmp_path / "snowflake_diff_project"
    prod_schema: str = build_unique_schema_name(prefix="sqlbuild_diff_prod")
    dev_schema: str = build_unique_schema_name(prefix="sqlbuild_diff_dev")
    database_name: str = str(build_snowflake_connection_config(schema=dev_schema)["database"])
    project_contents: str = (
        "name: snowflake_diff_project\n"
        "adapter: snowflake\n\n"
        "default_environment: dev\n\n"
        "connection:\n"
        "  account: ${ENV:SQB_TEST_SNOWFLAKE_ACCOUNT}\n"
        "  user: ${ENV:SQB_TEST_SNOWFLAKE_USER}\n"
        "  authenticator: ${ENV:SQB_TEST_SNOWFLAKE_AUTHENTICATOR}\n"
        "  token: ${ENV:SQB_TEST_SNOWFLAKE_PAT}\n"
        "  role: ${ENV:SQB_TEST_SNOWFLAKE_ROLE}\n"
        "  warehouse: ${ENV:SQB_TEST_SNOWFLAKE_WAREHOUSE}\n"
        "  database: ${ENV:SQB_TEST_SNOWFLAKE_DATABASE}\n\n"
        "environments:\n"
        f"  dev:\n    database: {database_name}\n    schema: {dev_schema}\n"
        f"  prod:\n    database: {database_name}\n    schema: {prod_schema}\n\n"
        "defaults:\n"
        "  materialized: table\n\n"
        "models/staging/stg_orders.sql: invalid\n"
    )
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "sqlbuild_project.yml").write_text(
        project_contents.replace(
            "models/staging/stg_orders.sql: invalid\n",
            "",
        ),
        encoding="utf-8",
    )
    models_dir: Path = project_dir / "models"
    staging_dir: Path = models_dir / "staging"
    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / "stg_orders.sql").write_text(
        "MODEL (materialized table, unique_key [order_id]);\n\n"
        "SELECT * FROM ("
        "SELECT 1 AS order_id, 1 AS customer_id, 100 AS amount_cents UNION ALL "
        "SELECT 2 AS order_id, 2 AS customer_id, 200 AS amount_cents"
        ")",
        encoding="utf-8",
    )
    return project_dir, prod_schema, dev_schema


def execute_snowflake_sql(*, schema_name: str, sql: str) -> None:
    """Execute mutating SQL against a Snowflake schema."""

    adapter: SnowflakeAdapter = SnowflakeAdapter()
    config: dict[str, object] = build_snowflake_connection_config(schema=schema_name)
    connection: Any = adapter.connect(config)
    try:
        adapter.execute(connection, sql)
    finally:
        adapter.close(connection)


def write_local_environment_override(*, project_dir: Path, environment: str) -> None:
    """Write a local environment override for Snowflake CLI e2e commands."""

    (project_dir / "sqlbuild_local.yml").write_text(
        f"environment: {environment}\n",
        encoding="utf-8",
    )
