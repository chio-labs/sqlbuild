from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from tests.e2e.src.sqlbuild.cli.commands.main.warehouses.harness import WarehouseHarness
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_source_loader_strategies,
    prepare_waffle_shop,
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


def prepare_sqlserver_waffle_shop(*, tmp_path: Path, config: dict[str, object]) -> tuple[Path, str]:
    schema_name: str = build_unique_schema_name(prefix="sqb_waffle")
    project_dir: Path = prepare_waffle_shop(tmp_path)

    (project_dir / "functions" / "sql" / "customer_orders.sql").unlink(missing_ok=True)
    (project_dir / "functions" / "python" / "is_completed_order_py.py").unlink(missing_ok=True)
    (project_dir / "tests" / "unit" / "test_customer_orders_table_fn.sql").unlink(missing_ok=True)
    (project_dir / "tests" / "unit" / "test_fact_orders.sql").unlink(missing_ok=True)
    (project_dir / "models" / "marts" / "daily_order_partitioned.sql").unlink(missing_ok=True)
    (project_dir / "tests" / "unit" / "test_is_completed_order_udf.sql").unlink(missing_ok=True)

    macro_path: Path = project_dir / "models" / "marts" / "_macros" / "python" / "time.py"
    _rewrite(
        macro_path,
        (
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
    )
    is_completed_order_path: Path = project_dir / "functions" / "sql" / "is_completed_order.sql"
    _rewrite(is_completed_order_path, ("STRING", "NVARCHAR"))
    _rewrite(is_completed_order_path, ("BOOLEAN", "BIT"))
    _rewrite(
        is_completed_order_path,
        (
            "order_status = 'completed'",
            "CAST(CASE WHEN order_status = 'completed' THEN 1 ELSE 0 END AS BIT)",
        ),
    )
    fact_orders_path: Path = project_dir / "models" / "marts" / "fact_orders.sql"
    _rewrite(
        fact_orders_path,
        (
            '__udf("is_completed_order_py")(o.status) AS is_completed_order_py,',
            '__udf("is_completed_order")(o.status) AS is_completed_order_py,',
        ),
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
    _rewrite(lookups_path, ("type: VARCHAR", "type: NVARCHAR(100)"))
    raw_sources_path: Path = project_dir / "sources" / "raw.yml"
    adapt_sqlserver_text_file(raw_sources_path)
    _rewrite(
        raw_sources_path,
        (
            "      - name: ordered_at\n        type: DATETIME2",
            "      - name: ordered_at\n        type: DATETIME",
        ),
    )
    return project_dir, schema_name


def _rewrite(path: Path, replacement: tuple[str, str]) -> None:
    """Replace text in a copied fixture file, failing when the fixture no longer contains it."""

    old, new = replacement
    text: str = path.read_text(encoding="utf-8")
    assert old in text, f"{path} no longer contains {old!r}; update the SQL Server fixture"
    path.write_text(text.replace(old, new), encoding="utf-8")


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
    loader_path: Path = project_dir / "python" / "loaders" / "strategy_sources.py"
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


def sqlserver_harness() -> WarehouseHarness:
    """Return the shared real-warehouse scenario hooks for SQL Server."""

    config: dict[str, object] = build_sqlserver_config()
    return WarehouseHarness(
        name="sqlserver",
        unique_schema=lambda prefix: build_unique_schema_name(prefix=prefix),
        project_toml=lambda project_name, schema_name: build_sqlserver_project_toml(
            project_name=project_name, schema_name=schema_name, config=config
        ),
        source_deferral_project_toml=lambda project_name, dev, prod: (
            build_sqlserver_source_deferral_project_toml(
                project_name=project_name,
                dev_schema_name=dev,
                prod_schema_name=prod,
                config=config,
            )
        ),
        ensure_schema=lambda schema_name: ensure_sqlserver_schema_ready(
            schema_name=schema_name, config=config
        ),
        cleanup_schema=lambda schema_name: cleanup_sqlserver_schema(
            schema_name=schema_name, config=config
        ),
        fetch_rows=lambda schema_name, sql: fetch_sqlserver_rows(sql=sql, config=config),
        execute_sql=lambda schema_name, sql: execute_sqlserver_sql(sql=sql, config=config),
        relation=lambda schema_name, name: relation_name(schema_name=schema_name, name=name),
        prepare_source_loader_strategies=lambda tmp_path: (
            prepare_sqlserver_source_loader_strategies(tmp_path=tmp_path, config=config)
        ),
        adapt_sql=adapt_sqlserver_sql,
        null_flag_sql=lambda expression: f"CASE WHEN {expression} IS NULL THEN 1 ELSE 0 END",
        true_text="1",
        false_text="0",
        text_type="NVARCHAR(100)",
        deferral_text_type="NVARCHAR(100)",
    )
