"""Helpers for ClickHouse CLI E2E tests."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from textwrap import dedent
from typing import Any, cast

from sqlbuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_waffle_shop

CLICKHOUSE_IMAGE: str = "clickhouse/clickhouse-server:26.1"


def build_unique_schema_name(*, prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def build_clickhouse_project_toml(
    *,
    project_name: str,
    schema_name: str,
    config: dict[str, object],
    extra: str = "",
) -> str:
    return (
        f'name = "{project_name}"\n'
        'adapter = "clickhouse"\n'
        'default_target = "dev"\n\n'
        "[connection]\n"
        f'host = "{config["host"]}"\n'
        f"port = {config['port']}\n"
        f'user = "{config["user"]}"\n'
        f'password = "{config["password"]}"\n\n'
        "[targets.dev]\n"
        f'schema = "{schema_name}"\n\n'
        "[defaults]\n"
        'materialized = "table"\n' + extra
    )


def execute_clickhouse_sql(*, config: dict[str, object], statements: tuple[str, ...]) -> None:
    adapter: ClickHouseAdapter = ClickHouseAdapter()
    connection: Any = adapter.connect(dict(config))
    try:
        for statement in statements:
            adapter.execute(connection=connection, sql=statement)
    finally:
        adapter.close(connection)


def fetch_clickhouse_rows(*, config: dict[str, object], sql: str) -> tuple[tuple[object, ...], ...]:
    adapter: ClickHouseAdapter = ClickHouseAdapter()
    connection: Any = adapter.connect(dict(config))
    try:
        cursor: Any = adapter.execute(connection=connection, sql=sql)
        return tuple(tuple(row) for row in cursor.fetchall())
    finally:
        adapter.close(connection)


def create_clickhouse_schema(*, config: dict[str, object], schema_name: str) -> None:
    execute_clickhouse_sql(
        config=config, statements=(f"CREATE DATABASE IF NOT EXISTS {schema_name}",)
    )


def cleanup_clickhouse_schema(*, config: dict[str, object], schema_name: str) -> None:
    rows: tuple[tuple[object, ...], ...] = fetch_clickhouse_rows(
        config=config,
        sql=(
            "SELECT name FROM system.functions WHERE origin = 'SQLUserDefined' "
            f"AND startsWith(name, '{schema_name}__')"
        ),
    )
    execute_clickhouse_sql(
        config=config,
        statements=(
            *(f"DROP FUNCTION IF EXISTS {row[0]}" for row in rows),
            f"DROP DATABASE IF EXISTS {schema_name} SYNC",
        ),
    )


def build_two_target_toml(
    *, project_name: str, prod_schema: str, dev_schema: str, config: dict[str, object]
) -> str:
    return (
        f'name = "{project_name}"\n'
        'adapter = "clickhouse"\n'
        'default_target = "dev"\n\n'
        "[connection]\n"
        f'host = "{config["host"]}"\n'
        f"port = {config['port']}\n"
        f'user = "{config["user"]}"\n'
        f'password = "{config["password"]}"\n\n'
        "[targets.prod]\n"
        f'schema = "{prod_schema}"\n\n'
        "[targets.prod.clone]\n"
        "allow_as_clone_destination = true\n\n"
        "[targets.dev]\n"
        f'schema = "{dev_schema}"\n\n'
        "[targets.dev.clone]\n"
        "allow_as_clone_origin = true\n"
    )


def build_orders_project_files(*, schema_name: str, config: dict[str, object]) -> dict[str, str]:
    return {
        "sqlbuild_project.toml": build_clickhouse_project_toml(
            project_name="clickhouse_orders",
            schema_name=schema_name,
            config=config,
            extra="\n[settings]\nconcurrency = 4\nmicrobatch_concurrency = true\n",
        ),
        "sources/raw.yml": dedent(
            f"""
            sources:
              - name: raw_events
                description: Synthetic order events.
                schema: {schema_name}
                table: raw_events
              - name: raw_customers
                description: Customer versions kept by a replacing engine.
                schema: {schema_name}
                table: raw_customers
                final: true
            """
        ).lstrip(),
        "seeds/regions.csv": "customer_id,region_name\n1,north\n2,south\n3,east\n",
        "seeds/regions.yml": dedent(
            """
            seeds:
              - name: regions
                description: Customer regions.
                columns:
                  - name: customer_id
                    type: Int64
                  - name: region_name
                    type: String
            """
        ).lstrip(),
        "functions/sql/half_amount.sql": (
            'FUNCTION (\n  description "Half of an amount",\n'
            "  arguments (amount Int64),\n  returns Float64,\n);\n\namount / 2\n"
        ),
        "models/stg_events.sql": (
            "MODEL (description 'Staged events.', materialized view);\n\n"
            "SELECT event_id, customer_id, amount, event_time\n"
            'FROM __source("raw_events")\n'
        ),
        "models/customer_totals.sql": (
            "MODEL (description 'One row per customer.');\n\n"
            "SELECT e.customer_id AS customer_id, r.region_name AS region_name,\n"
            "  sum(e.amount) AS total_amount,\n"
            '  __udf("half_amount")(sum(e.amount)) AS half_total\n'
            'FROM __ref("stg_events") AS e\n'
            'JOIN __seed("regions") AS r ON e.customer_id = r.customer_id\n'
            "GROUP BY e.customer_id, r.region_name\n"
        ),
        "models/customer_names.sql": (
            "MODEL (description 'One row per customer name.');\n\n"
            'SELECT customer_id, customer_name FROM __source("raw_customers")\n'
        ),
        "models/customer_latest.sql": (
            "MODEL (description 'Latest activity per customer.',\n"
            "  materialized incremental,\n"
            "  incremental_strategy merge,\n"
            "  unique_key [customer_id],\n"
            ");\n\n"
            "SELECT customer_id, count() AS event_count, max(event_time) AS last_event_time\n"
            'FROM __ref("stg_events")\n'
            "GROUP BY customer_id\n"
        ),
        "models/daily_events.sql": (
            "MODEL (description 'Events by day.',\n"
            "  materialized incremental,\n"
            "  incremental_strategy delete_insert,\n"
            "  incremental_mode microbatch,\n"
            "  microbatch_strategy watermark,\n"
            "  cursor_watermark_mode all,\n"
            "  cursor event_time,\n"
            "  cursor_type timestamp,\n"
            "  cursor_grain hour,\n"
            "  cursor_inputs (\n"
            "    raw_events (column event_time, roles [filter, watermark]),\n"
            "  ),\n"
            "  batch_size 1d,\n"
            "  batch_concurrency 4,\n"
            ");\n\n"
            "SELECT event_id, customer_id, amount, event_time\n"
            'FROM __source("raw_events")\n'
            "WHERE event_time >= __cursor_start() AND event_time < __cursor_end()\n"
        ),
    }


def build_partitioned_events_project_files(
    *, schema_name: str, config: dict[str, object], partition_by: str = "toYYYYMM(event_time)"
) -> dict[str, str]:
    return {
        "sqlbuild_project.toml": build_clickhouse_project_toml(
            project_name="clickhouse_layout", schema_name=schema_name, config=config
        ),
        "sources/raw.yml": dedent(
            f"""
            sources:
              - name: raw_events
                description: Synthetic order events.
                schema: {schema_name}
                table: raw_events
            """
        ).lstrip(),
        "models/events.sql": (
            "MODEL (description 'One row per event.',\n"
            "  materialized incremental,\n"
            "  incremental_strategy delete_insert,\n"
            "  unique_key [event_id],\n"
            "  cursor event_time,\n"
            "  cursor_type timestamp,\n"
            "  cursor_grain hour,\n"
            "  cursor_inputs (\n"
            "    raw_events event_time,\n"
            "  ),\n"
            "  engine 'ReplacingMergeTree(version)',\n"
            "  order_by [event_id, event_time],\n"
            "  partition_by 'toYYYYMM(event_time)',\n"
            "  primary_key [event_id],\n"
            "  table_settings (index_granularity 4096),\n"
            ");\n\n"
            "SELECT event_id, amount, event_time, toInt64(1) AS version\n"
            'FROM __source("raw_events")\n'
            "WHERE event_time >= __cursor_start() AND event_time < __cursor_end()\n"
        ),
    }


def active_parts_by_partition(
    *, config: dict[str, object], schema_name: str, table: str
) -> dict[str, tuple[str, ...]]:
    rows: tuple[tuple[object, ...], ...] = fetch_clickhouse_rows(
        config=config,
        sql=(
            "SELECT partition, arraySort(groupArray(name)) FROM system.parts "
            f"WHERE active AND database = '{schema_name}' AND table = '{table}' "
            "GROUP BY partition ORDER BY partition"
        ),
    )
    return {str(row[0]): tuple(map(str, cast(list[object], row[1]))) for row in rows}


def prepare_clickhouse_waffle_shop(
    *, tmp_path: Path, config: dict[str, object]
) -> tuple[Path, str]:
    """Copy waffle shop to tmp dir and wire it to a unique ClickHouse database."""

    schema_name: str = build_unique_schema_name(prefix="sqb_waffle")
    project_dir: Path = prepare_waffle_shop(tmp_path)
    (project_dir / "functions" / "sql" / "customer_orders.sql").unlink()
    (project_dir / "tests" / "unit" / "test_customer_orders_table_fn.sql").unlink()
    (project_dir / "functions" / "python" / "is_completed_order_py.py").unlink()
    fact_orders_path: Path = project_dir / "models" / "marts" / "fact_orders.sql"
    fact_orders_path.write_text(
        fact_orders_path.read_text(encoding="utf-8").replace(
            '__udf("is_completed_order_py")(o.status) AS is_completed_order_py,',
            '__udf("is_completed_order")(o.status) AS is_completed_order_py,',
        ),
        encoding="utf-8",
    )
    for model_name in ("dim_customers", "fact_orders", "scenario_order_prices"):
        _alias_qualified_columns(project_dir / "models" / "marts" / f"{model_name}.sql")
    materialization_path: Path = project_dir / "materializations" / "partition_tracked.py"
    materialization_path.write_text(
        materialization_path.read_text(encoding="utf-8").replace(
            "CURRENT_TIMESTAMP", "CURRENT_TIMESTAMP()"
        ),
        encoding="utf-8",
    )
    time_macros_path: Path = project_dir / "models" / "marts" / "_macros" / "time.py"
    time_macros_path.write_text(
        time_macros_path.read_text(encoding="utf-8").replace(
            "return f\"DATE_TRUNC('{grain}', {expression})\"",
            "return f\"CAST(DATE_TRUNC('{grain}', {expression}) AS TIMESTAMP)\"",
        ),
        encoding="utf-8",
    )
    (project_dir / "sqlbuild_project.toml").write_text(
        build_clickhouse_project_toml(
            project_name="waffle_shop",
            schema_name=schema_name,
            config=config,
            extra='\n[settings]\ndefault_audit_severity = "warn"\n\n'
            '[path_defaults.staging]\nmaterialized = "view"\n',
        ),
        encoding="utf-8",
    )
    return project_dir, schema_name


def _alias_qualified_columns(model_path: Path) -> None:
    """Alias bare qualified columns; ClickHouse names them ``alias.column`` in multi-joins."""

    model_path.write_text(
        re.sub(
            r"^(\s+)(\w+)\.(\w+),$",
            r"\1\2.\3 AS \3,",
            model_path.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        ),
        encoding="utf-8",
    )
