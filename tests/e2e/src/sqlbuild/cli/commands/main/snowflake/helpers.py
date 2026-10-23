"""Helpers for Snowflake CLI e2e tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from tests.e2e.src.sqlbuild.cli.commands.main.warehouses.harness import WarehouseHarness
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_source_loader_strategies,
    prepare_waffle_shop,
)
from tests.integration.src.sqlbuild.adapters.snowflake.helpers import (
    build_snowflake_connection_config,
    build_unique_schema_name,
    create_schema_if_missing,
    fetch_rows,
    qualified_name,
)


def build_snowflake_local_config(*, schema_name: str) -> str:
    """Build a local config pointing the example project at Snowflake."""

    return (
        'adapter = "snowflake"\n\n'
        "[connection]\n"
        'account = "${ENV:SQB_TEST_SNOWFLAKE_ACCOUNT}"\n'
        'user = "${ENV:SQB_TEST_SNOWFLAKE_USER}"\n'
        'authenticator = "${ENV:SQB_TEST_SNOWFLAKE_AUTHENTICATOR}"\n'
        'token = "${ENV:SQB_TEST_SNOWFLAKE_PAT}"\n'
        'role = "${ENV:SQB_TEST_SNOWFLAKE_ROLE}"\n'
        'warehouse = "${ENV:SQB_TEST_SNOWFLAKE_WAREHOUSE}"\n'
        'database = "${ENV:SQB_TEST_SNOWFLAKE_DATABASE}"\n'
        f'schema = "{schema_name}"\n'
    )


def build_snowflake_project_toml(*, project_name: str, schema_name: str) -> str:
    """Build project TOML for an inline Snowflake e2e project."""

    database_name: str = str(build_snowflake_connection_config(schema=schema_name)["database"])
    return (
        f'name = "{project_name}"\n'
        'adapter = "snowflake"\n'
        'default_target = "dev"\n\n'
        "[connection]\n"
        'account = "${ENV:SQB_TEST_SNOWFLAKE_ACCOUNT}"\n'
        'user = "${ENV:SQB_TEST_SNOWFLAKE_USER}"\n'
        'authenticator = "${ENV:SQB_TEST_SNOWFLAKE_AUTHENTICATOR}"\n'
        'token = "${ENV:SQB_TEST_SNOWFLAKE_PAT}"\n'
        'role = "${ENV:SQB_TEST_SNOWFLAKE_ROLE}"\n'
        'warehouse = "${ENV:SQB_TEST_SNOWFLAKE_WAREHOUSE}"\n'
        'database = "${ENV:SQB_TEST_SNOWFLAKE_DATABASE}"\n\n'
        "[targets.dev]\n"
        f'database = "{database_name}"\n'
        f'schema = "{schema_name}"\n'
        'defer_sources_to = "dev"\n\n'
        "[defaults]\n"
        'materialized = "table"\n'
    )


def build_snowflake_source_deferral_project_toml(
    *, project_name: str, dev_schema_name: str, prod_schema_name: str
) -> str:
    database_name: str = str(build_snowflake_connection_config(schema=dev_schema_name)["database"])
    return (
        f'name = "{project_name}"\n'
        'adapter = "snowflake"\n'
        'default_target = "dev"\n\n'
        "[connection]\n"
        'account = "${ENV:SQB_TEST_SNOWFLAKE_ACCOUNT}"\n'
        'user = "${ENV:SQB_TEST_SNOWFLAKE_USER}"\n'
        'authenticator = "${ENV:SQB_TEST_SNOWFLAKE_AUTHENTICATOR}"\n'
        'token = "${ENV:SQB_TEST_SNOWFLAKE_PAT}"\n'
        'role = "${ENV:SQB_TEST_SNOWFLAKE_ROLE}"\n'
        'warehouse = "${ENV:SQB_TEST_SNOWFLAKE_WAREHOUSE}"\n'
        'database = "${ENV:SQB_TEST_SNOWFLAKE_DATABASE}"\n\n'
        "[targets.dev]\n"
        f'database = "{database_name}"\n'
        f'schema = "{dev_schema_name}"\n'
        'defer_sources_to = "prod"\n\n'
        "[targets.prod]\n"
        f'database = "{database_name}"\n'
        f'schema = "{prod_schema_name}"\n\n'
        "[defaults]\n"
        'materialized = "table"\n'
    )


def prepare_snowflake_waffle_shop(*, tmp_path: Path) -> tuple[Path, str]:
    """Prepare a Waffle Shop project wired to a unique Snowflake schema."""

    project_dir: Path = prepare_waffle_shop(tmp_path)
    schema_name: str = build_unique_schema_name(prefix="sqlbuild_e2e")
    database_name: str = str(build_snowflake_connection_config(schema=schema_name)["database"])
    project_file_path: Path = project_dir / "sqlbuild_project.toml"
    project_contents: str = (
        'name = "waffle_shop"\n'
        'adapter = "duckdb"\n'
        'default_target = "dev"\n\n'
        "[connection]\n"
        'database = "waffle_shop.duckdb"\n\n'
        "[settings]\n"
        'default_audit_severity = "warn"\n\n'
        "[defaults]\n"
        'materialized = "table"\n\n'
        "[targets.dev]\n"
        f'database = "{database_name}"\n'
        f'schema = "{schema_name}"\n'
        'defer_sources_to = "dev"\n\n'
        "[targets.prod]\n"
        f'database = "{database_name}"\n'
        f'schema = "{schema_name}"\n\n'
        "[path_defaults.staging]\n"
        'materialized = "view"\n'
    )
    project_file_path.write_text(project_contents, encoding="utf-8")
    (project_dir / "sqlbuild_local.toml").write_text(
        build_snowflake_local_config(schema_name=schema_name),
        encoding="utf-8",
    )
    return project_dir, schema_name


def prepare_snowflake_source_loader_strategies(*, tmp_path: Path) -> tuple[Path, str]:
    """Prepare source-loader strategy fixture wired to a unique Snowflake schema."""

    schema_name: str = build_unique_schema_name(prefix="sqlbuild_e2e_load")
    project_dir: Path = prepare_source_loader_strategies(
        tmp_path=tmp_path,
        project_toml=build_snowflake_project_toml(
            project_name="source_loader_strategies",
            schema_name=schema_name,
        ),
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
            connection=connection,
            sql=f"DROP SCHEMA IF EXISTS {database_name}.{schema_name} CASCADE",
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


def list_snowflake_scenario_relation_names(*, schema_name: str) -> tuple[str, ...]:
    """Return scenario artifact relation names in a Snowflake schema."""

    database_name: str = str(build_snowflake_connection_config(schema=schema_name)["database"])
    rows: tuple[tuple[object, ...], ...] = fetch_snowflake_rows(
        schema_name=schema_name,
        sql=(
            f"SELECT LOWER(table_name) FROM {database_name}.information_schema.tables "
            f"WHERE UPPER(table_schema) = UPPER('{schema_name}') "
            "AND LOWER(table_name) LIKE '__sqb_%' ORDER BY LOWER(table_name)"
        ),
    )
    return tuple(str(row[0]) for row in rows)


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
        'name = "snowflake_diff_project"\n'
        'adapter = "snowflake"\n'
        'default_target = "dev"\n\n'
        "[connection]\n"
        'account = "${ENV:SQB_TEST_SNOWFLAKE_ACCOUNT}"\n'
        'user = "${ENV:SQB_TEST_SNOWFLAKE_USER}"\n'
        'authenticator = "${ENV:SQB_TEST_SNOWFLAKE_AUTHENTICATOR}"\n'
        'token = "${ENV:SQB_TEST_SNOWFLAKE_PAT}"\n'
        'role = "${ENV:SQB_TEST_SNOWFLAKE_ROLE}"\n'
        'warehouse = "${ENV:SQB_TEST_SNOWFLAKE_WAREHOUSE}"\n'
        'database = "${ENV:SQB_TEST_SNOWFLAKE_DATABASE}"\n\n'
        "[targets.dev]\n"
        f'database = "{database_name}"\n'
        f'schema = "{dev_schema}"\n\n'
        "[targets.dev.clone]\n"
        "allow_as_clone_origin = true\n"
        "allow_as_clone_destination = true\n\n"
        "[targets.prod]\n"
        f'database = "{database_name}"\n'
        f'schema = "{prod_schema}"\n\n'
        "[targets.prod.clone]\n"
        "allow_as_clone_origin = true\n"
        "allow_as_clone_destination = false\n\n"
        "[defaults]\n"
        'materialized = "table"\n\n'
        "models/staging/stg_orders.sql: invalid\n"
    )
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "sqlbuild_project.toml").write_text(
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
        "MODEL (description 'Test model stg_orders.', "
        "materialized table, unique_key [order_id]);\n\n"
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
        adapter.execute(connection=connection, sql=sql)
    finally:
        adapter.close(connection)


def write_local_environment_override(*, project_dir: Path, environment: str) -> None:
    """Write a local environment override for Snowflake CLI e2e commands."""

    (project_dir / "sqlbuild_local.toml").write_text(
        f'target = "{environment}"\n',
        encoding="utf-8",
    )


def build_snowflake_dbt_profiles_yml(*, schema_name: str, config: dict[str, object]) -> str:
    """Build a dbt profiles.yml pointing analytics/dev at the Snowflake warehouse."""

    return (
        "analytics:\n"
        "  target: dev\n"
        "  outputs:\n"
        "    dev:\n"
        "      type: snowflake\n"
        f"      account: {config['account']}\n"
        f"      user: {config['user']}\n"
        "      authenticator: programmatic_access_token\n"
        f"      token: {config['token']}\n"
        f"      role: {config['role']}\n"
        f"      warehouse: {config['warehouse']}\n"
        f"      database: {config['database']}\n"
        f"      schema: {schema_name}\n"
    )


def write_snowflake_dbt_scenario_date_trunc_model(*, sqlbuild_project_dir: Path) -> None:
    """Write a Snowflake-flavored DATE_TRUNC dbt model and a scenario targeting it."""

    dbt_models_dir: Path = sqlbuild_project_dir.parent / "dbt_project" / "models"
    dbt_models_dir.joinpath("event_rollup.sql").write_text(
        "select\n"
        "  customer_id,\n"
        "  date_trunc('DAY', event_ts) as event_day,\n"
        "  count(*) as event_count\n"
        "from {{ source('raw', 'events') }}\n"
        "group by customer_id, date_trunc('DAY', event_ts)\n",
        encoding="utf-8",
    )
    dbt_models_dir.joinpath("schema.yml").write_text(
        "version: 2\nsources:\n  - name: raw\n    tables:\n      - name: events\n",
        encoding="utf-8",
    )
    scenarios_dir: Path = sqlbuild_project_dir / "tests" / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)
    scenarios_dir.joinpath("dbt_event_rollup.sql").write_text(
        'SCENARIO (description "dbt date_trunc scenario", tags ["dbt"]);\n\n'
        "WITH\n"
        "__source__raw__events AS (\n"
        "  SELECT 10 AS customer_id,"
        " TO_TIMESTAMP_NTZ('2026-01-01 08:15:00') AS event_ts\n"
        "  UNION ALL\n"
        "  SELECT 10 AS customer_id,"
        " TO_TIMESTAMP_NTZ('2026-01-01 10:30:00') AS event_ts\n"
        "),\n"
        "__expected__event_rollup AS (\n"
        "  SELECT 10 AS customer_id,"
        " DATE_TRUNC('DAY', TO_TIMESTAMP_NTZ('2026-01-01 00:00:00')) AS event_day,"
        " 2 AS event_count\n"
        ")\n"
        "SELECT 1\n",
        encoding="utf-8",
    )


def snowflake_harness() -> WarehouseHarness:
    """Return the shared real-warehouse scenario hooks for Snowflake."""

    return WarehouseHarness(
        name="snowflake",
        unique_schema=lambda prefix: build_unique_schema_name(prefix=prefix),
        project_toml=lambda project_name, schema_name: build_snowflake_project_toml(
            project_name=project_name, schema_name=schema_name
        ),
        source_deferral_project_toml=lambda project_name, dev, prod: (
            build_snowflake_source_deferral_project_toml(
                project_name=project_name, dev_schema_name=dev, prod_schema_name=prod
            )
        ),
        ensure_schema=lambda schema_name: ensure_query_schema_ready(schema_name=schema_name),
        cleanup_schema=lambda schema_name: cleanup_snowflake_schema(schema_name=schema_name),
        fetch_rows=lambda schema_name, sql: fetch_snowflake_rows(schema_name=schema_name, sql=sql),
        execute_sql=lambda schema_name, sql: execute_snowflake_sql(
            schema_name=schema_name, sql=sql
        ),
        relation=lambda schema_name, name: relation_name(schema_name=schema_name, name=name),
        prepare_source_loader_strategies=lambda tmp_path: (
            prepare_snowflake_source_loader_strategies(tmp_path=tmp_path)
        ),
        local_files=lambda schema_name: {
            "sqlbuild_local.toml": build_snowflake_local_config(schema_name=schema_name)
        },
        seeds_with_ctas=True,
        dlt_schemas=lambda schema_base: (f"{schema_base}_MODELS", f"{schema_base}_raw".lower()),
        scenario_relation_names=lambda schema_name: list_snowflake_scenario_relation_names(
            schema_name=schema_name
        ),
    )
