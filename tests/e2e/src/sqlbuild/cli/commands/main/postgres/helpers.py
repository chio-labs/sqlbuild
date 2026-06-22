"""Helpers for Postgres CLI e2e tests."""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.postgres.client import PostgresAdapter
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    assert_dbt_seeded_reuse_from_lifecycle,
    assert_dbt_snapshot_seeded_reuse_from_lifecycle,
    prepare_source_loader_strategies,
    prepare_waffle_shop,
    stringify_warehouse_rows,
)


def build_unique_schema_name(*, prefix: str) -> str:
    suffix: str = uuid.uuid4().hex[:10]
    return f"{prefix}_{suffix}"


def postgres_dbt_core_executable() -> str:
    """Return a dbt-core executable for Postgres dbt tests, skipping otherwise.

    dbt Fusion does not support the Postgres adapter, so these tests must pin to
    the dbt-core CLI installed in the project virtual environment rather than
    honoring any DBT_EXECUTABLE override that may point at Fusion.
    """

    candidate: Path = Path(sys.prefix) / "bin" / "dbt"
    if not candidate.exists():
        pytest.skip("dbt-core CLI is not installed in the project virtual environment")
    result: subprocess.CompletedProcess[str] = subprocess.run(
        (str(candidate), "--version"),
        capture_output=True,
        check=False,
        text=True,
    )
    output: str = result.stdout + result.stderr
    if result.returncode != 0:
        pytest.skip(f"dbt-core CLI is not runnable: {output}")
    if "fusion" in output.lower():
        pytest.skip("project virtual environment dbt resolves to Fusion, which lacks Postgres")
    return str(candidate)


def postgres_dbt_env(*, password: str) -> dict[str, str]:
    """Return the subprocess env for Postgres dbt tests pinned to dbt-core."""

    return {
        "DBT_POSTGRES_PASSWORD": password,
        "DBT_EXECUTABLE": postgres_dbt_core_executable(),
    }


def build_postgres_project_toml(
    *,
    project_name: str,
    schema_name: str,
    config: dict[str, object],
) -> str:
    return (
        f'name = "{project_name}"\n'
        'adapter = "postgres"\n'
        'default_target = "dev"\n\n'
        "[connection]\n"
        f'host = "{config["host"]}"\n'
        f"port = {config['port']}\n"
        f'dbname = "{config["dbname"]}"\n'
        f'user = "{config["user"]}"\n'
        f'password = "{config["password"]}"\n\n'
        "[targets.dev]\n"
        f'schema = "{schema_name}"\n'
        'defer_sources_to = "dev"\n\n'
        "[defaults]\n"
        'materialized = "table"\n'
    )


def build_postgres_dependency_baseline_project_toml(
    *, project_name: str, dev_schema_name: str, prod_schema_name: str, config: dict[str, object]
) -> str:
    return (
        f'name = "{project_name}"\n'
        'adapter = "postgres"\n'
        'default_target = "dev"\n\n'
        "[connection]\n"
        f'host = "{config["host"]}"\n'
        f"port = {config['port']}\n"
        f'dbname = "{config["dbname"]}"\n'
        f'user = "{config["user"]}"\n'
        f'password = "{config["password"]}"\n\n'
        "[targets.prod]\n"
        f'schema = "{prod_schema_name}"\n\n'
        "[targets.dev]\n"
        f'schema = "{dev_schema_name}"\n'
        'reuse_from = "prod"\n'
        "reuse_hard_copy = true\n\n"
        "[defaults]\n"
        'materialized = "table"\n'
    )


def assert_postgres_seeded_reuse_case(
    *,
    tmp_path: Path,
    schema_prefix: str,
    expected_rows: tuple[tuple[object, ...], ...],
    postgres_e2e_config: dict[str, object],
    snapshot: bool,
) -> None:
    schema_base: str = build_unique_schema_name(prefix=schema_prefix)
    dev_schema_name: str = f"{schema_base}_dev"
    prod_schema_name: str = f"{schema_base}_prod"
    env: dict[str, str] = postgres_dbt_env(password=str(postgres_e2e_config["password"]))
    try:
        ensure_postgres_schema_ready(schema_name=dev_schema_name, config=postgres_e2e_config)
        ensure_postgres_schema_ready(schema_name=prod_schema_name, config=postgres_e2e_config)
        relation: str = "orders_snapshot" if snapshot else "fact_orders"
        current_filter: str = " WHERE dbt_valid_to IS NULL" if snapshot else ""
        profiles_yml: str = _postgres_reuse_profiles_yml(
            config=postgres_e2e_config,
            dev_schema_name=dev_schema_name,
            prod_schema_name=prod_schema_name,
        )
        project_toml: str = _postgres_reuse_project_toml(
            config=postgres_e2e_config,
            dev_schema_name=dev_schema_name,
        )
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
        raw_orders_relation: str = relation_name(schema_name=dev_schema_name, name="raw_orders")
        if snapshot:
            assert_dbt_snapshot_seeded_reuse_from_lifecycle(
                tmp_path=tmp_path,
                profiles_yml=profiles_yml,
                project_toml=project_toml,
                origin_snapshot_schema=prod_schema_name,
                destination_snapshot_schema=dev_schema_name,
                fetch_rows=lambda sql: fetch_postgres_rows(config=postgres_e2e_config, sql=sql),
                execute_sql=lambda sql: execute_postgres_sql(config=postgres_e2e_config, sql=sql),
                raw_orders_relation=raw_orders_relation,
                destination_rows_sql=destination_rows_sql,
                downstream_rows_sql=downstream_rows_sql,
                expected_rows=expected_rows,
                env=env,
            )
        else:
            assert_dbt_seeded_reuse_from_lifecycle(
                tmp_path=tmp_path,
                profiles_yml=profiles_yml,
                project_toml=project_toml,
                fetch_rows=lambda sql: fetch_postgres_rows(config=postgres_e2e_config, sql=sql),
                execute_sql=lambda sql: execute_postgres_sql(config=postgres_e2e_config, sql=sql),
                raw_orders_relation=raw_orders_relation,
                destination_rows_sql=destination_rows_sql,
                downstream_rows_sql=downstream_rows_sql,
                expected_rows=expected_rows,
                env=env,
            )
    finally:
        cleanup_postgres_schema(schema_name=dev_schema_name, config=postgres_e2e_config)
        cleanup_postgres_schema(schema_name=prod_schema_name, config=postgres_e2e_config)


def _postgres_reuse_profiles_yml(
    *, config: dict[str, object], dev_schema_name: str, prod_schema_name: str
) -> str:
    return (
        "analytics:\n"
        "  target: dev\n"
        "  outputs:\n"
        "    dev:\n"
        "      type: postgres\n"
        f"      host: {config['host']}\n"
        f"      port: {config['port']}\n"
        f"      dbname: {config['dbname']}\n"
        f"      user: {config['user']}\n"
        "      pass: \"{{ env_var('DBT_POSTGRES_PASSWORD') }}\"\n"
        f"      schema: {dev_schema_name}\n"
        "    prod:\n"
        "      type: postgres\n"
        f"      host: {config['host']}\n"
        f"      port: {config['port']}\n"
        f"      dbname: {config['dbname']}\n"
        f"      user: {config['user']}\n"
        "      pass: \"{{ env_var('DBT_POSTGRES_PASSWORD') }}\"\n"
        f"      schema: {prod_schema_name}\n"
    )


def _postgres_reuse_project_toml(*, config: dict[str, object], dev_schema_name: str) -> str:
    return (
        build_postgres_project_toml(
            project_name="postgres_dbt_reuse_from",
            schema_name=dev_schema_name,
            config=config,
        )
        + "\n[dbt]\n"
        + 'project_dir = "../dbt_project"\n'
        + 'profiles_dir = "../profiles"\n'
        + 'target_path = "../dbt_project/target"\n'
        + "[dbt.reuse_from]\n"
        + 'git_ref = "prod"\n'
        + 'generate_schema_name_override = "dbt/macros/prod_generate_schema_name.sql"\n'
    )


def build_postgres_virtual_project_toml(
    *,
    project_name: str,
    config: dict[str, object],
    state_schema: str,
    warehouse_schema: str,
    unsuffixed_virtual_env: str | None = None,
) -> str:
    unsuffixed_line: str = (
        f'unsuffixed_virtual_env = "{unsuffixed_virtual_env}"\n'
        if unsuffixed_virtual_env is not None
        else ""
    )
    return (
        f'name = "{project_name}"\n'
        'adapter = "postgres"\n'
        'default_target = "dev"\n\n'
        "[settings]\n"
        "virtual_environments = true\n"
        "[connection]\n"
        f'host = "{config["host"]}"\n'
        f"port = {config['port']}\n"
        f'dbname = "{config["dbname"]}"\n'
        f'user = "{config["user"]}"\n'
        f'password = "{config["password"]}"\n\n'
        "[targets.dev]\n"
        f'schema = "{warehouse_schema}"\n\n'
        "[targets.dev.state]\n"
        'backend = "postgres"\n'
        f'schema = "{state_schema}"\n'
        f"{unsuffixed_line}\n"
        "[targets.dev.state.connection]\n"
        f'host = "{config["host"]}"\n'
        f"port = {config['port']}\n"
        f'dbname = "{config["dbname"]}"\n'
        f'user = "{config["user"]}"\n'
        f'password = "{config["password"]}"\n'
    )


def build_postgres_virtual_plan_repo_files(
    *,
    project_name: str,
    config: dict[str, object],
    state_schema: str,
    warehouse_schema: str,
    stg_orders_sql: str,
    dim_customers_sql: str = "SELECT 1 AS customer_id",
    extra_project_toml: str = "",
) -> dict[str, str]:
    return {
        "sqlbuild_project.toml": build_postgres_virtual_project_toml(
            project_name=project_name,
            config=config,
            state_schema=state_schema,
            warehouse_schema=warehouse_schema,
        )
        + extra_project_toml,
        "models/stg_orders.sql": f"MODEL ();\n\n{stg_orders_sql}\n",
        "models/fact_orders.sql": 'MODEL ();\n\nSELECT id FROM __ref("stg_orders")\n',
        "models/dim_customers.sql": f"MODEL ();\n\n{dim_customers_sql}\n",
    }


def build_postgres_virtual_clone_project_toml(
    *,
    project_name: str,
    config: dict[str, object],
    prod_state_schema: str,
    dev_state_schema: str,
    prod_warehouse_schema: str,
    dev_warehouse_schema: str,
) -> str:
    connection_toml: str = (
        f'host = "{config["host"]}"\n'
        f"port = {config['port']}\n"
        f'dbname = "{config["dbname"]}"\n'
        f'user = "{config["user"]}"\n'
        f'password = "{config["password"]}"\n'
    )
    return (
        f'name = "{project_name}"\n'
        'adapter = "postgres"\n'
        'default_target = "dev"\n\n'
        "[settings]\n"
        "virtual_environments = true\n"
        "[connection]\n"
        f"{connection_toml}\n"
        "[targets.prod]\n"
        f'schema = "{prod_warehouse_schema}"\n\n'
        "[targets.prod.clone]\n"
        "allow_as_clone_origin = true\n\n"
        "[targets.prod.state]\n"
        'backend = "postgres"\n'
        f'schema = "{prod_state_schema}"\n\n'
        "[targets.prod.state.connection]\n"
        f"{connection_toml}\n"
        "[targets.dev]\n"
        f'schema = "{dev_warehouse_schema}"\n\n'
        "[targets.dev.clone]\n"
        "allow_as_clone_destination = true\n\n"
        "[targets.dev.state]\n"
        'backend = "postgres"\n'
        f'schema = "{dev_state_schema}"\n\n'
        "[targets.dev.state.connection]\n"
        f"{connection_toml}"
    )


def build_postgres_source_deferral_project_toml(
    *, project_name: str, dev_schema_name: str, prod_schema_name: str, config: dict[str, object]
) -> str:
    return (
        f'name = "{project_name}"\n'
        'adapter = "postgres"\n'
        'default_target = "dev"\n\n'
        "[connection]\n"
        f'host = "{config["host"]}"\n'
        f"port = {config['port']}\n"
        f'dbname = "{config["dbname"]}"\n'
        f'user = "{config["user"]}"\n'
        f'password = "{config["password"]}"\n\n'
        "[targets.dev]\n"
        f'schema = "{dev_schema_name}"\n'
        'defer_sources_to = "prod"\n\n'
        "[targets.prod]\n"
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


def cleanup_postgres_state_schemas(*, schema_name: str, config: dict[str, object]) -> None:
    adapter: PostgresAdapter = PostgresAdapter()
    connection: Any = adapter.connect(config)
    try:
        adapter.execute(
            connection, f"DROP SCHEMA IF EXISTS {quote_identifier(schema_name)} CASCADE"
        )
        cursor: Any = adapter.execute(
            connection,
            "SELECT schema_name FROM information_schema.schemata "
            f"WHERE schema_name LIKE '{schema_name}__backup_%'",
        )
        backup_schemas: tuple[str, ...] = tuple(str(row[0]) for row in cursor.fetchall())
        backup_schema: str
        for backup_schema in backup_schemas:
            adapter.execute(
                connection,
                f"DROP SCHEMA IF EXISTS {quote_identifier(backup_schema)} CASCADE",
            )
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


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def quoted_relation_name(*, schema_name: str, name: str) -> str:
    return f"{quote_identifier(schema_name)}.{quote_identifier(name)}"


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
        'default_target = "dev"\n\n'
        "[connection]\n"
        f'host = "{config["host"]}"\n'
        f"port = {config['port']}\n"
        f'dbname = "{config["dbname"]}"\n'
        f'user = "{config["user"]}"\n'
        f'password = "{config["password"]}"\n\n'
        "[targets.dev]\n"
        f'schema = "{dev_schema}"\n\n'
        "[targets.dev.clone]\n"
        "allow_as_clone_origin = true\n"
        "allow_as_clone_destination = true\n\n"
        "[targets.prod]\n"
        f'schema = "{prod_schema}"\n\n'
        "[targets.prod.clone]\n"
        "allow_as_clone_origin = true\n"
        "allow_as_clone_destination = false\n\n"
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
        'default_target = "dev"\n\n'
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
        "[targets.dev]\n"
        f'schema = "{schema_name}"\n'
        'defer_sources_to = "dev"\n\n'
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


def prepare_postgres_dbt_seed_change_workspace(
    *, tmp_path: Path, schema_name: str, config: dict[str, object]
) -> Path:
    """Write a pure dbt seed-backed model chain on a Postgres dbt profile.

    Chain: seed raw_orders -> stg_orders -> fct_orders. Returns the SQLBuild twin dir.
    """

    workspace: Path = tmp_path / "pg_seed_change"
    dbt_project_dir: Path = workspace / "dbt_project"
    profiles_dir: Path = workspace / "profiles"
    sqlbuild_project_dir: Path = workspace / "sqlbuild_project"
    dbt_models_dir: Path = dbt_project_dir / "models"
    dbt_seeds_dir: Path = dbt_project_dir / "seeds"
    dbt_models_dir.mkdir(parents=True)
    dbt_seeds_dir.mkdir(parents=True)
    profiles_dir.mkdir(parents=True)
    sqlbuild_project_dir.mkdir(parents=True)
    (profiles_dir / "profiles.yml").write_text(
        "analytics:\n"
        "  target: dev\n"
        "  outputs:\n"
        "    dev:\n"
        "      type: postgres\n"
        f"      host: {config['host']}\n"
        f"      port: {config['port']}\n"
        f"      dbname: {config['dbname']}\n"
        f"      user: {config['user']}\n"
        "      pass: \"{{ env_var('DBT_POSTGRES_PASSWORD') }}\"\n"
        f"      schema: {schema_name}\n",
        encoding="utf-8",
    )
    (dbt_project_dir / "dbt_project.yml").write_text(
        "name: analytics\n"
        "version: '1.0'\n"
        "profile: analytics\n"
        "model-paths: ['models']\n"
        "seed-paths: ['seeds']\n"
        "models:\n"
        "  analytics:\n"
        "    +materialized: table\n",
        encoding="utf-8",
    )
    (dbt_seeds_dir / "raw_orders.csv").write_text(
        "order_id,amount\n1,25\n2,20\n3,30\n", encoding="utf-8"
    )
    (dbt_models_dir / "stg_orders.sql").write_text(
        "select order_id, amount from {{ ref('raw_orders') }}\n", encoding="utf-8"
    )
    (dbt_models_dir / "fct_orders.sql").write_text(
        "select count(*) as order_count, sum(amount) as total_amount "
        "from {{ ref('stg_orders') }}\n",
        encoding="utf-8",
    )
    (sqlbuild_project_dir / "sqlbuild_project.toml").write_text(
        'name = "pg_seed_change"\n'
        'adapter = "postgres"\n'
        'default_target = "dev"\n'
        "[connection]\n"
        f'host = "{config["host"]}"\n'
        f"port = {config['port']}\n"
        f'dbname = "{config["dbname"]}"\n'
        f'user = "{config["user"]}"\n'
        f'password = "{config["password"]}"\n'
        "[targets.dev]\n"
        f'schema = "{schema_name}"\n'
        "[dbt]\n"
        'project_dir = "../dbt_project"\n'
        'profiles_dir = "../profiles"\n'
        'target_path = "../dbt_project/target"\n',
        encoding="utf-8",
    )
    return sqlbuild_project_dir


def append_postgres_dbt_seed_change_order(*, project_dir: Path, order_id: int, amount: int) -> None:
    """Append one row to the Postgres seed-change raw_orders seed."""

    seed_path: Path = project_dir.parent / "dbt_project" / "seeds" / "raw_orders.csv"
    seed_path.write_text(
        seed_path.read_text(encoding="utf-8") + f"{order_id},{amount}\n",
        encoding="utf-8",
    )
