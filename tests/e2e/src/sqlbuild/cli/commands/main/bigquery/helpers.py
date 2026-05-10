"""Helpers for BigQuery CLI e2e tests."""

from __future__ import annotations

from pathlib import Path
from shutil import copytree
from typing import Any

from sqlbuild.integrations.bigquery.client import BigQueryAdapter
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import REPO_ROOT
from tests.integration.src.sqlbuild.integrations.bigquery.helpers import (
    build_bigquery_connection_config,
    build_unique_dataset_name,
    fetch_rows,
    qualified_name,
)

EXAMPLE_WAFFLE_SHOP_DIR: Path = REPO_ROOT / "examples" / "waffle_shop"


def build_bigquery_local_config(*, environment: str = "dev", location: str) -> str:
    """Build a local config pointing the project at BigQuery."""

    return (
        'adapter = "bigquery"\n'
        f'environment = "{environment}"\n\n'
        "[connection]\n"
        'project = "${ENV:SQB_TEST_BIGQUERY_PROJECT}"\n'
        f'location = "{location}"\n'
    )


def build_bigquery_project_toml(*, project_name: str, dataset_name: str) -> str:
    """Build project TOML for an inline BigQuery e2e project."""

    project_id: str = str(build_bigquery_connection_config(schema=dataset_name)["project"])
    location: str = str(build_bigquery_connection_config(schema=dataset_name)["location"])
    return (
        f'name = "{project_name}"\n'
        'adapter = "bigquery"\n'
        'default_environment = "dev"\n\n'
        "[connection]\n"
        'project = "${ENV:SQB_TEST_BIGQUERY_PROJECT}"\n'
        f'location = "{location}"\n\n'
        "[environments.dev]\n"
        f'database = "{project_id}"\n'
        f'schema = "{dataset_name}"\n\n'
        "[defaults]\n"
        'materialized = "table"\n'
    )


def prepare_bigquery_waffle_shop(*, tmp_path: Path) -> tuple[Path, str]:
    """Prepare the example waffle shop project wired to a unique BigQuery dataset."""

    project_dir: Path = tmp_path / "waffle_shop"
    copytree(EXAMPLE_WAFFLE_SHOP_DIR, project_dir)
    dataset_name: str = build_unique_dataset_name(prefix="sqlbuild_e2e")
    project_name: str = str(build_bigquery_connection_config(schema=dataset_name)["project"])
    location: str = str(build_bigquery_connection_config(schema=dataset_name)["location"])
    project_contents: str = (
        'name = "waffle_shop"\n'
        'adapter = "bigquery"\n'
        'default_environment = "dev"\n\n'
        "[connection]\n"
        'project = "${ENV:SQB_TEST_BIGQUERY_PROJECT}"\n'
        f'location = "{location}"\n\n'
        "[settings]\n"
        'default_audit_severity = "warn"\n\n'
        "[defaults]\n"
        'materialized = "table"\n\n'
        "[environments.dev]\n"
        f'database = "{project_name}"\n'
        f'schema = "{dataset_name}"\n\n'
        "[environments.prod]\n"
        f'database = "{project_name}"\n'
        f'schema = "{dataset_name}"\n\n'
        "[path_defaults.staging]\n"
        'materialized = "view"\n'
    )
    (project_dir / "sqlbuild_project.toml").write_text(project_contents, encoding="utf-8")
    (project_dir / "sqlbuild_local.toml").write_text(
        build_bigquery_local_config(location=location),
        encoding="utf-8",
    )
    return project_dir, dataset_name


def cleanup_bigquery_dataset(*, dataset_name: str) -> None:
    """Drop the generated BigQuery dataset after a test completes."""

    adapter: BigQueryAdapter = BigQueryAdapter()
    config: dict[str, object] = build_bigquery_connection_config(schema=dataset_name)
    project_name: str = str(config["project"])
    connection: Any = adapter.connect(config)
    try:
        connection.client.delete_dataset(
            f"{project_name}.{dataset_name}",
            delete_contents=True,
            not_found_ok=True,
        )
    finally:
        adapter.close(connection)


def ensure_bigquery_dataset_ready(*, dataset_name: str) -> None:
    """Precreate the dataset for commands that write directly into it."""

    adapter: BigQueryAdapter = BigQueryAdapter()
    config: dict[str, object] = build_bigquery_connection_config(schema=dataset_name)
    project_name: str = str(config["project"])
    connection: Any = adapter.connect(config)
    try:
        from google.cloud import bigquery

        dataset: Any = bigquery.Dataset(f"{project_name}.{dataset_name}")
        dataset.location = connection.location
        connection.client.create_dataset(dataset, exists_ok=True)
    finally:
        adapter.close(connection)


def fetch_bigquery_rows(*, dataset_name: str, sql: str) -> tuple[tuple[object, ...], ...]:
    """Fetch rows from BigQuery using the configured test credentials."""

    adapter: BigQueryAdapter = BigQueryAdapter()
    config: dict[str, object] = build_bigquery_connection_config(schema=dataset_name)
    connection: Any = adapter.connect(config)
    try:
        return fetch_rows(adapter=adapter, connection=connection, sql=sql)
    finally:
        adapter.close(connection)


def relation_name(*, dataset_name: str, name: str) -> str:
    """Return a fully qualified relation name for a BigQuery e2e dataset."""

    project_name: str = str(build_bigquery_connection_config(schema=dataset_name)["project"])
    return qualified_name(project=project_name, dataset=dataset_name, name=name)


def prepare_bigquery_query_source(*, dataset_name: str) -> str:
    """Create a simple source table used by query CLI tests."""

    table_name: str = relation_name(dataset_name=dataset_name, name="query_source")
    execute_bigquery_sql(
        dataset_name=dataset_name,
        sql=(
            f"CREATE OR REPLACE TABLE {table_name} AS "
            "SELECT 1 AS id, 'alice' AS name UNION ALL SELECT 2 AS id, 'bob' AS name"
        ),
    )
    return table_name


def prepare_bigquery_diff_project(*, tmp_path: Path) -> tuple[Path, str, str]:
    """Prepare a BigQuery-backed diff project with explicit prod/dev target datasets."""

    project_dir: Path = tmp_path / "bigquery_diff_project"
    prod_dataset: str = build_unique_dataset_name(prefix="sqlbuild_diff_prod")
    dev_dataset: str = build_unique_dataset_name(prefix="sqlbuild_diff_dev")
    project_name: str = str(build_bigquery_connection_config(schema=dev_dataset)["project"])
    location: str = str(build_bigquery_connection_config(schema=dev_dataset)["location"])
    project_contents: str = (
        'name = "bigquery_diff_project"\n'
        'adapter = "bigquery"\n'
        'default_environment = "dev"\n\n'
        "[connection]\n"
        'project = "${ENV:SQB_TEST_BIGQUERY_PROJECT}"\n'
        f'location = "{location}"\n\n'
        "[environments.dev]\n"
        f'database = "{project_name}"\n'
        f'schema = "{dev_dataset}"\n\n'
        "[environments.prod]\n"
        f'database = "{project_name}"\n'
        f'schema = "{prod_dataset}"\n\n'
        "[defaults]\n"
        'materialized = "table"\n'
    )
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "sqlbuild_project.toml").write_text(project_contents, encoding="utf-8")
    (project_dir / "sqlbuild_local.toml").write_text(
        build_bigquery_local_config(location=location),
        encoding="utf-8",
    )
    models_dir: Path = project_dir / "models" / "staging"
    models_dir.mkdir(parents=True, exist_ok=True)
    (models_dir / "stg_orders.sql").write_text(
        "MODEL (\n"
        "  materialized table,\n"
        "  unique_key [order_id],\n"
        "  cursor order_id,\n"
        "  cursor_type integer\n"
        ");\n\n"
        "SELECT * FROM ("
        "SELECT 1 AS order_id, 1 AS customer_id, 100 AS amount_cents UNION ALL "
        "SELECT 2 AS order_id, 2 AS customer_id, 200 AS amount_cents"
        ")",
        encoding="utf-8",
    )
    return project_dir, prod_dataset, dev_dataset


def execute_bigquery_sql(*, dataset_name: str, sql: str) -> None:
    """Execute mutating SQL against a BigQuery dataset."""

    adapter: BigQueryAdapter = BigQueryAdapter()
    config: dict[str, object] = build_bigquery_connection_config(schema=dataset_name)
    connection: Any = adapter.connect(config)
    try:
        ensure_bigquery_dataset_ready(dataset_name=dataset_name)
        adapter.execute(connection, sql)
    finally:
        adapter.close(connection)


def write_local_environment_override(*, project_dir: Path, environment: str) -> None:
    """Write a local environment override for BigQuery CLI e2e commands."""

    location: str = str(build_bigquery_connection_config()["location"])
    (project_dir / "sqlbuild_local.toml").write_text(
        build_bigquery_local_config(environment=environment, location=location),
        encoding="utf-8",
    )
