"""Helpers for Databricks CLI e2e tests."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Any

from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from tests.e2e.src.sqlbuild.cli.commands.main.warehouses.harness import WarehouseHarness
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_source_loader_strategies,
    prepare_waffle_shop,
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

    timing_contexts: dict[bool, Callable[[str], AbstractContextManager[None]]] = {
        False: _unreported_databricks_timing,
        True: _reported_databricks_timing,
    }
    with timing_contexts[os.environ.get("SQB_E2E_TIMING") == "1"](label):
        yield


@contextmanager
def _unreported_databricks_timing(label: str) -> Iterator[None]:
    del label
    yield


@contextmanager
def _reported_databricks_timing(label: str) -> Iterator[None]:
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
        adapter.execute(
            connection=connection,
            sql=f"CREATE SCHEMA IF NOT EXISTS `{catalog_name}`.`{schema_name}`",
        )
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
            connection=connection,
            sql=f"DROP SCHEMA IF EXISTS `{catalog_name}`.`{schema_name}` CASCADE",
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
        "MODEL (description 'Test model stg_orders.', "
        "materialized table, unique_key [order_id]);\n\n"
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
        adapter.execute(connection=connection, sql=sql)
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


def databricks_harness() -> WarehouseHarness:
    """Return the shared real-warehouse scenario hooks for Databricks."""

    return WarehouseHarness(
        name="databricks",
        unique_schema=lambda prefix: build_unique_schema_name(prefix=prefix),
        project_toml=lambda project_name, schema_name: build_databricks_project_toml(
            project_name=project_name, schema_name=schema_name
        ),
        ensure_schema=lambda schema_name: ensure_databricks_schema_ready(schema_name=schema_name),
        cleanup_schema=lambda schema_name: cleanup_databricks_schema(schema_name=schema_name),
        fetch_rows=lambda schema_name, sql: fetch_databricks_rows(schema_name=schema_name, sql=sql),
        execute_sql=lambda schema_name, sql: execute_databricks_sql(
            schema_name=schema_name, sql=sql
        ),
        relation=lambda schema_name, name: relation_name(schema_name=schema_name, name=name),
        prepare_source_loader_strategies=lambda tmp_path: (
            prepare_databricks_source_loader_strategies(tmp_path=tmp_path)
        ),
        timing=databricks_e2e_timing,
        source_location_yaml=lambda schema_name: (
            f"    database: {build_databricks_connection_config(schema=schema_name)['catalog']}\n"
            f"    schema: {schema_name}\n"
        ),
        scenario_relation_names=lambda schema_name: list_databricks_scenario_relation_names(
            schema_name=schema_name
        ),
    )
