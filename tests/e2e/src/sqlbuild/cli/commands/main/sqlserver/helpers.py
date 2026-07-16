from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path
from typing import Any

from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from tests.e2e.src.sqlbuild.cli.commands.main.sqlserver._test_types import (
    SqlServerDependencyBaselineE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    prepare_source_loader_strategies,
    prepare_waffle_shop,
    run_sqb,
    stringify_warehouse_rows,
)


def build_unique_schema_name(*, prefix: str) -> str:
    suffix: str = uuid.uuid4().hex[:10]
    return f"{prefix}_{suffix}"


def build_sqlserver_config() -> dict[str, object]:
    return {
        "host": os.environ.get("SQLBUILD_SQLSERVER_HOST", "localhost"),
        "port": int(os.environ.get("SQLBUILD_SQLSERVER_PORT", "1433")),
        "database": os.environ.get("SQLBUILD_SQLSERVER_DATABASE", "tempdb"),
        "user": os.environ.get("SQLBUILD_SQLSERVER_USER", "sa"),
        "password": os.environ.get("SQLBUILD_SQLSERVER_PASSWORD", "Sqlbuild!2026"),
    }


def build_sqlserver_project_toml(
    *, project_name: str, schema_name: str, config: dict[str, object]
) -> str:
    return (
        f'name = "{project_name}"\n'
        'adapter = "sqlserver"\n'
        'default_target = "dev"\n\n'
        "[connection]\n"
        f'host = "{config["host"]}"\n'
        f"port = {config['port']}\n"
        f'database = "{config["database"]}"\n'
        f'user = "{config["user"]}"\n'
        f'password = "{config["password"]}"\n\n'
        "[targets.dev]\n"
        f'schema = "{schema_name}"\n'
        'defer_sources_to = "dev"\n\n'
        "[defaults]\n"
        'materialized = "table"\n'
    )


def build_sqlserver_dependency_baseline_project_toml(
    *, project_name: str, dev_schema_name: str, prod_schema_name: str, config: dict[str, object]
) -> str:
    return (
        f'name = "{project_name}"\n'
        'adapter = "sqlserver"\n'
        'default_target = "dev"\n\n'
        "[connection]\n"
        f'host = "{config["host"]}"\n'
        f"port = {config['port']}\n"
        f'database = "{config["database"]}"\n'
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


def assert_sqlserver_dependency_baseline_case(
    *, tmp_path: Path, test_case: SqlServerDependencyBaselineE2ETestCase
) -> None:
    schema_base: str = build_unique_schema_name(prefix=test_case.schema_prefix)
    dev_schema_name: str = f"{schema_base}_dev"
    prod_schema_name: str = f"{schema_base}_prod"
    config: dict[str, object] = build_sqlserver_config()
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="sqlserver_dependency_baseline",
        repo_files={
            "sqlbuild_project.toml": build_sqlserver_dependency_baseline_project_toml(
                project_name="sqlserver_dependency_baseline",
                dev_schema_name=dev_schema_name,
                prod_schema_name=prod_schema_name,
                config=config,
            ),
            "models/upstream.sql": (
                "MODEL (materialized table);\n\nSELECT 1 AS id, 900 AS amount\n"
            ),
            "models/downstream.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT id, amount AS downstream_amount FROM __ref("upstream")\n'
            ),
        },
    )
    try:
        ensure_sqlserver_schema_ready(schema_name=dev_schema_name, config=config)
        ensure_sqlserver_schema_ready(schema_name=prod_schema_name, config=config)
        (project_dir / "sqlbuild_local.toml").write_text('target = "prod"\n', encoding="utf-8")
        prod_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build", "--select", "upstream"),
            project_dir=project_dir,
        )
        assert prod_result.returncode == 0, prod_result.stdout + prod_result.stderr
        (project_dir / "sqlbuild_local.toml").write_text('target = "dev"\n', encoding="utf-8")

        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        expected_fragment: str
        for expected_fragment in test_case.expected_stdout_fragments:
            assert expected_fragment in result.stdout
        absent_fragment: str
        for absent_fragment in test_case.expected_absent_stdout_fragments:
            assert absent_fragment not in result.stdout
        assert (
            fetch_sqlserver_rows(
                sql=(
                    "SELECT id, amount FROM "
                    f"{relation_name(schema_name=dev_schema_name, name='upstream')} ORDER BY id"
                ),
                config=config,
            )
            == test_case.expected_upstream_rows
        )
        assert (
            fetch_sqlserver_rows(
                sql=(
                    "SELECT id, downstream_amount FROM "
                    f"{relation_name(schema_name=dev_schema_name, name='downstream')} ORDER BY id"
                ),
                config=config,
            )
            == test_case.expected_downstream_rows
        )
        assert (
            fetch_sqlserver_rows(
                sql=(
                    "SELECT node_type, node_name FROM "
                    f"{relation_name(schema_name=dev_schema_name, name='_sqlbuild_fingerprints')} "
                    "WHERE node_type = 'model' ORDER BY node_name"
                ),
                config=config,
            )
            == test_case.expected_fingerprint_rows
        )
    finally:
        cleanup_sqlserver_schema(schema_name=dev_schema_name, config=config)
        cleanup_sqlserver_schema(schema_name=prod_schema_name, config=config)


def build_sqlserver_virtual_project_toml(
    *,
    project_name: str,
    schema_name: str,
    config: dict[str, object],
    unsuffixed_virtual_env: str | None = None,
) -> str:
    unsuffixed_line: str = {None: ""}.get(
        unsuffixed_virtual_env,
        f'unsuffixed_virtual_env = "{unsuffixed_virtual_env}"\n',
    )
    return (
        f'name = "{project_name}"\n'
        'adapter = "sqlserver"\n'
        'default_target = "dev"\n\n'
        "[settings]\n"
        "virtual_environments = true\n"
        "[connection]\n"
        f'host = "{config["host"]}"\n'
        f"port = {config['port']}\n"
        f'database = "{config["database"]}"\n'
        f'user = "{config["user"]}"\n'
        f'password = "{config["password"]}"\n\n'
        "[targets.dev]\n"
        f'schema = "{schema_name}"\n\n'
        "[targets.dev.state]\n"
        'backend = "duckdb"\n'
        'schema = "sqlbuild_state"\n'
        f"{unsuffixed_line}\n"
        "[targets.dev.state.connection]\n"
        'database = "state.duckdb"\n'
    )


def build_sqlserver_source_deferral_project_toml(
    *, project_name: str, dev_schema_name: str, prod_schema_name: str, config: dict[str, object]
) -> str:
    return (
        f'name = "{project_name}"\n'
        'adapter = "sqlserver"\n'
        'default_target = "dev"\n\n'
        "[connection]\n"
        f'host = "{config["host"]}"\n'
        f"port = {config['port']}\n"
        f'database = "{config["database"]}"\n'
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


def relation_name(*, schema_name: str, name: str) -> str:
    return f"[{schema_name}].[{name}]"


def adapt_sqlserver_project_files(repo_files: dict[str, str]) -> dict[str, str]:
    return {path: adapt_sqlserver_sql(contents) for path, contents in repo_files.items()}


def adapt_sqlserver_sql(sql: str) -> str:
    return (
        sql.replace(" AS TIMESTAMP", " AS DATETIME2")
        .replace("type: TIMESTAMP", "type: DATETIME2")
        .replace("plan", "plan_name")
    )


def adapt_sqlserver_text_file(path: Path) -> None:
    path.write_text(adapt_sqlserver_sql(path.read_text(encoding="utf-8")), encoding="utf-8")


def ensure_sqlserver_schema_ready(*, schema_name: str, config: dict[str, object]) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()
    connection: Any = adapter.connect(config)
    try:
        adapter.execute(
            connection=connection, sql=f"CREATE SCHEMA {adapter.render_identifier(schema_name)}"
        )
    finally:
        adapter.close(connection)


def execute_sqlserver_sql(*, sql: str, config: dict[str, object]) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()
    connection: Any = adapter.connect(config)
    try:
        adapter.execute(connection=connection, sql=sql)
    finally:
        adapter.close(connection)


def cleanup_sqlserver_schema(*, schema_name: str, config: dict[str, object]) -> None:
    adapter: SqlServerAdapter = SqlServerAdapter()
    connection: Any = adapter.connect(config)
    escaped_schema_name: str = schema_name.replace("'", "''")
    try:
        adapter.execute(
            connection=connection,
            sql="DECLARE @sql NVARCHAR(MAX) = N''; "
            "SELECT @sql += N'DROP FUNCTION ' + QUOTENAME(s.name) "
            "+ N'.' + QUOTENAME(o.name) + N';' "
            "FROM sys.objects o JOIN sys.schemas s ON o.schema_id = s.schema_id "
            f"WHERE s.name = '{escaped_schema_name}' AND o.type IN ('FN', 'IF', 'TF'); "
            "EXEC sp_executesql @sql;",
        )
        adapter.execute(
            connection=connection,
            sql="DECLARE @sql NVARCHAR(MAX) = N''; "
            "SELECT @sql += N'DROP VIEW ' + QUOTENAME(s.name) + N'.' + QUOTENAME(v.name) + N';' "
            "FROM sys.views v JOIN sys.schemas s ON v.schema_id = s.schema_id "
            f"WHERE s.name = '{escaped_schema_name}'; "
            "EXEC sp_executesql @sql;",
        )
        adapter.execute(
            connection=connection,
            sql="DECLARE @sql NVARCHAR(MAX) = N''; "
            "SELECT @sql += N'DROP TABLE ' + QUOTENAME(s.name) + N'.' + QUOTENAME(t.name) + N';' "
            "FROM sys.tables t JOIN sys.schemas s ON t.schema_id = s.schema_id "
            f"WHERE s.name = '{escaped_schema_name}'; "
            "EXEC sp_executesql @sql;",
        )
        adapter.execute(
            connection=connection,
            sql=f"IF SCHEMA_ID(N'{escaped_schema_name}') IS NOT NULL "
            f"DROP SCHEMA {adapter.render_identifier(schema_name)}",
        )
    finally:
        adapter.close(connection)


def fetch_sqlserver_rows(*, sql: str, config: dict[str, object]) -> tuple[tuple[object, ...], ...]:
    adapter: SqlServerAdapter = SqlServerAdapter()
    connection: Any = adapter.connect(config)
    try:
        cursor: Any = adapter.execute(connection=connection, sql=sql)
        return tuple(tuple(row) for row in cursor.fetchall())
    finally:
        adapter.close(connection)


def assert_current_sqlserver_snapshot_rows_from_case(
    *,
    schema_name: str,
    config: dict[str, object],
    expected_rows: tuple[tuple[object, ...], ...],
) -> None:
    assert_current_sqlserver_snapshot_rows(
        schema_name=schema_name,
        config=config,
        expected_rows=expected_rows,
    )


def assert_current_sqlserver_snapshot_rows(
    *,
    schema_name: str,
    config: dict[str, object],
    expected_rows: tuple[tuple[object, ...], ...],
) -> None:
    rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
        sql=(
            "SELECT customer_id, region_id, plan_name, "
            "CAST(effective_from AS DATE), CAST(effective_to AS DATE) "
            f"FROM {relation_name(schema_name=schema_name, name='current_customer_snapshot')} "
            "ORDER BY customer_id, region_id, effective_from"
        ),
        config=config,
    )
    assert stringify_warehouse_rows(rows) == expected_rows


def assert_sqlserver_snapshot_matrix_rows(
    *,
    schema_name: str,
    config: dict[str, object],
    expected_current_rows: tuple[tuple[object, ...], ...],
    expected_historical_timestamp_rows: tuple[tuple[object, ...], ...],
    expected_historical_check_rows: tuple[tuple[object, ...], ...],
) -> None:
    assert_current_sqlserver_snapshot_rows(
        schema_name=schema_name,
        config=config,
        expected_rows=expected_current_rows,
    )
    historical_timestamp_rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
        sql=(
            "SELECT customer_id, plan_name, CAST(valid_from AS DATE), CAST(valid_to AS DATE) "
            f"FROM {relation_name(schema_name=schema_name, name='historical_customer_snapshot')} "
            "ORDER BY customer_id, valid_from"
        ),
        config=config,
    )
    historical_check_rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
        sql=(
            "SELECT customer_id, status, CAST(valid_from AS DATE), CAST(valid_to AS DATE) "
            f"FROM {relation_name(schema_name=schema_name, name='historical_membership_snapshot')} "
            "ORDER BY customer_id, valid_from"
        ),
        config=config,
    )
    assert stringify_warehouse_rows(historical_timestamp_rows) == expected_historical_timestamp_rows
    assert stringify_warehouse_rows(historical_check_rows) == expected_historical_check_rows


def assert_sqlserver_snapshot_apply_rows(
    *,
    schema_name: str,
    config: dict[str, object],
    expected_current_check_rows: tuple[tuple[object, ...], ...],
    expected_current_delete_rows: tuple[tuple[object, ...], ...],
    expected_historical_timestamp_rows: tuple[tuple[object, ...], ...],
    expected_historical_check_rows: tuple[tuple[object, ...], ...],
) -> None:
    current_check_rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
        sql=(
            "SELECT customer_id, status, CASE WHEN valid_to IS NULL THEN 1 ELSE 0 END "
            f"FROM {relation_name(schema_name=schema_name, name='current_check_snapshot')} "
            "ORDER BY customer_id, status, CASE WHEN valid_to IS NULL THEN 1 ELSE 0 END"
        ),
        config=config,
    )
    current_delete_rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
        sql=(
            "SELECT customer_id, plan_name, CASE WHEN valid_to IS NULL THEN 1 ELSE 0 END "
            f"FROM {relation_name(schema_name=schema_name, name='current_delete_snapshot')} "
            "ORDER BY customer_id, plan_name, CASE WHEN valid_to IS NULL THEN 1 ELSE 0 END"
        ),
        config=config,
    )
    historical_timestamp_rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
        sql=(
            "SELECT customer_id, plan_name, CAST(valid_from AS DATE), CAST(valid_to AS DATE) "
            f"FROM {relation_name(schema_name=schema_name, name='historical_timestamp_snapshot')} "
            "ORDER BY customer_id, valid_from"
        ),
        config=config,
    )
    historical_check_rows: tuple[tuple[object, ...], ...] = fetch_sqlserver_rows(
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


def prepare_sqlserver_waffle_shop(*, tmp_path: Path, config: dict[str, object]) -> tuple[Path, str]:
    schema_name: str = build_unique_schema_name(prefix="sqb_waffle")
    project_dir: Path = prepare_waffle_shop(tmp_path)

    (project_dir / "functions" / "sql" / "customer_orders.sql").unlink(missing_ok=True)
    (project_dir / "functions" / "python" / "is_completed_order_py.py").unlink(missing_ok=True)
    (project_dir / "tests" / "unit" / "test_customer_orders_table_fn.sql").unlink(missing_ok=True)
    (project_dir / "models" / "marts" / "daily_order_partitioned.sql").unlink(missing_ok=True)
    (project_dir / "tests" / "unit" / "test_is_completed_order_udf.sql").unlink(missing_ok=True)

    macro_path: Path = project_dir / "macros" / "time.py"
    macro_path.write_text(
        macro_path.read_text(encoding="utf-8").replace(
            '    if ctx.adapter_name == "bigquery":\n'
            '        return f"TIMESTAMP_TRUNC({expression}, {grain.upper()})"\n'
            "    return f\"DATE_TRUNC('{grain}', {expression})\"",
            '    if ctx.adapter_name == "bigquery":\n'
            '        return f"TIMESTAMP_TRUNC({expression}, {grain.upper()})"\n'
            '    if ctx.adapter_name == "sqlserver":\n'
            "        if grain == 'hour':\n"
            '            return f"DATEADD(hour, DATEDIFF(hour, 0, {expression}), 0)"\n'
            "        if grain == 'day':\n"
            '            return f"CAST(CAST({expression} AS DATE) AS DATETIME2)"\n'
            "    return f\"DATE_TRUNC('{grain}', {expression})\"",
        ),
        encoding="utf-8",
    )
    is_completed_order_path: Path = project_dir / "functions" / "sql" / "is_completed_order.sql"
    is_completed_order_path.write_text(
        is_completed_order_path.read_text(encoding="utf-8")
        .replace("STRING", "NVARCHAR")
        .replace("BOOLEAN", "BIT")
        .replace(
            "order_status = 'completed'",
            "CAST(CASE WHEN order_status = 'completed' THEN 1 ELSE 0 END AS BIT)",
        ),
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
        build_sqlserver_project_toml(
            project_name="waffle_shop",
            schema_name=schema_name,
            config=config,
        )
        + (
            '\n[settings]\ndefault_audit_severity = "warn"\n\n'
            '[path_defaults.staging]\nmaterialized = "view"\n'
        ),
        encoding="utf-8",
    )
    lookups_path: Path = project_dir / "seeds" / "lookups.yml"
    lookups_path.write_text(
        lookups_path.read_text(encoding="utf-8").replace("type: VARCHAR", "type: NVARCHAR(100)"),
        encoding="utf-8",
    )
    adapt_sqlserver_text_file(project_dir / "sources" / "raw.yml")
    for test_path in (project_dir / "tests" / "unit").glob("*.sql"):
        test_path.unlink(missing_ok=True)
    return project_dir, schema_name


def prepare_sqlserver_source_loader_strategies(
    *, tmp_path: Path, config: dict[str, object]
) -> tuple[Path, str]:
    schema_name: str = build_unique_schema_name(prefix="sqb_load")
    project_dir: Path = prepare_source_loader_strategies(
        tmp_path=tmp_path,
        project_toml=build_sqlserver_project_toml(
            project_name="source_loader_strategies",
            schema_name=schema_name,
            config=config,
        ),
    )
    source_path: Path = project_dir / "sources" / "raw.yml"
    source_path.write_text(
        source_path.read_text(encoding="utf-8").replace("type: TIMESTAMP", "type: DATETIME2"),
        encoding="utf-8",
    )
    loader_path: Path = project_dir / "loaders" / "strategy_sources.py"
    old_sql: str = (
        'f"CREATE TABLE {ctx.destination} AS "\n'
        "        \"SELECT 1 AS status_id, 'loaded' AS status_name, "
        "'self_managed' AS loaded_by\""
    )
    new_sql: str = (
        "\"SELECT 1 AS status_id, 'loaded' AS status_name, 'self_managed' AS loaded_by \"\n"
        '        f"INTO {ctx.destination}"'
    )
    loader_path.write_text(
        loader_path.read_text(encoding="utf-8").replace(old_sql, new_sql),
        encoding="utf-8",
    )
    return project_dir, schema_name
