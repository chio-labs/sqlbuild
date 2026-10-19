"""Helpers for ClickHouse CLI E2E tests."""

from __future__ import annotations

import uuid
from textwrap import dedent
from typing import Any

from sqlbuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter

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
