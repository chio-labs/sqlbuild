"""Helpers for ClickHouse CLI E2E tests."""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from textwrap import dedent
from typing import Any, cast

from sqlbuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_waffle_shop
from tests.integration.src.sqlbuild.cli.recall.helpers import write_project

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


RECALL_TABLES: tuple[str, ...] = (
    "recall_meta",
    "recall_invocations",
    "recall_output",
    "recall_events",
    "recall_diagnostics",
    "recall_artifacts",
    "recall_artifact_refs",
    "recall_heartbeats",
    "recall_delivery",
    "recall_conflicts",
)
_TTL_DAYS: re.Pattern[str] = re.compile(r" TTL \w+ \+ toIntervalDay\((\d+)\)")
_AGED_TABLES: tuple[tuple[str, str], ...] = (
    ("recall_invocations", ""),
    ("recall_output", ""),
    ("recall_events", ", concat('aged-', event_id) AS event_id"),
    ("recall_diagnostics", ""),
    ("recall_artifact_refs", ""),
    ("recall_heartbeats", ""),
    ("recall_delivery", ""),
    ("recall_conflicts", ""),
)


def recall_store_toml(
    *,
    config: dict[str, object],
    database: str,
    recall_settings: str = "",
    connection_settings: str = "",
) -> str:
    """Project configuration sending Recall history to a ClickHouse database."""

    return (
        "\n[connections.history]\n"
        'adapter = "clickhouse"\n'
        f'host = "{config["host"]}"\n'
        f"port = {config['port']}\n"
        f'user = "{config["user"]}"\n'
        f'password = "{config["password"]}"\n'
        f'database = "{database}"\n'
        f"{connection_settings}"
        "\n[recall]\n"
        'connection = "history"\n'
        f"{recall_settings}"
    )


def stored_ttl_days(*, config: dict[str, object], database: str) -> tuple[tuple[str, int], ...]:
    """Each Recall table's TTL in days, by table name."""

    rows: tuple[tuple[object, ...], ...] = fetch_clickhouse_rows(
        config=config,
        sql=(
            "SELECT name, create_table_query FROM system.tables "
            f"WHERE database = '{database}' AND startsWith(name, 'recall_') ORDER BY name"
        ),
    )
    return tuple(
        (str(name), int(next(iter(_TTL_DAYS.findall(str(query))), -1))) for name, query in rows
    )


def physical_rows(*, config: dict[str, object], database: str, where: str = "1") -> int:
    """Rows stored across every Recall table, before any deduplication or retention filter."""

    total: int = 0
    for table in RECALL_TABLES:
        rows: tuple[tuple[object, ...], ...] = fetch_clickhouse_rows(
            config=config, sql=f"SELECT count() FROM {database}.{table} WHERE {where}"
        )
        total += int(cast(int, rows[0][0]))
    return total


def age_recorded_invocations(*, config: dict[str, object], database: str, days: int) -> None:
    """Store a copy of every invocation's rows started `days` earlier, under `aged-` IDs."""

    statements: list[str] = []
    for table, extra in _AGED_TABLES:
        replaced: str = (
            "concat('aged-', invocation_id) AS invocation_id, "
            f"invocation_started_at - INTERVAL {days} DAY AS invocation_started_at{extra}"
        )
        statements.append(
            f"INSERT INTO {database}.{table} SELECT * REPLACE ({replaced}) FROM "
            f"(SELECT * FROM {database}.{table} WHERE NOT startsWith(invocation_id, 'aged-'))"
        )
    execute_clickhouse_sql(config=config, statements=tuple(statements))


def expire_recall_parts(*, config: dict[str, object], database: str) -> None:
    """Apply every Recall table's TTL now, as background TTL merges eventually would."""

    execute_clickhouse_sql(
        config=config,
        statements=tuple(
            f"ALTER TABLE {database}.{table} MATERIALIZE TTL SETTINGS mutations_sync = 2"
            for table in RECALL_TABLES
        ),
    )


def apply_printed_retention_fix(*, config: dict[str, object], stderr: str) -> int:
    """Run the statements a retention notice printed without expiring stored parts."""

    script: str = stderr.split("configured retention with:\n\n", 1)[1].split("\nsqb ", 1)[0]
    statements: list[str] = [
        statement.strip().removesuffix(";") for statement in script.split(";\n\n")
    ]
    import clickhouse_connect

    client: Any = clickhouse_connect.get_client(
        host=str(config["host"]),
        port=int(cast(int, config["port"])),
        username=str(config["user"]),
        password=str(config["password"]),
    )
    try:
        for statement in statements:
            client.command(statement, settings={"materialize_ttl_after_modify": 0})
    finally:
        client.close()
    return len(statements)


def apply_printed_ddl(*, config: dict[str, object], stderr: str) -> None:
    """Run, as an administrator, the script a permission notice printed for creating the store."""

    script: str = stderr.split(" with:\n\n", 1)[1].split("\nsqb ", 1)[0].strip()
    execute_clickhouse_sql(
        config=config,
        statements=tuple(
            statement.strip().removesuffix(";") for statement in script.split(";\n\n")
        ),
    )


@contextmanager
def limited_user(
    *, config: dict[str, object], database: str, revoked_inserts: tuple[str, ...] = ()
) -> Iterator[dict[str, object]]:
    """A user with only `SELECT` and `INSERT` on `database`, less `revoked_inserts`."""

    name: str = build_unique_schema_name(prefix="recall_writer")
    password: str = uuid.uuid4().hex
    execute_clickhouse_sql(
        config=config,
        statements=(
            f"CREATE USER {name} IDENTIFIED BY '{password}'",
            f"GRANT SELECT, INSERT ON {database}.* TO {name}",
            *(f"REVOKE INSERT ON {database}.{table} FROM {name}" for table in revoked_inserts),
        ),
    )
    try:
        yield {**config, "user": name, "password": password}
    finally:
        execute_clickhouse_sql(config=config, statements=(f"DROP USER IF EXISTS {name}",))


def duplicate_recall_rows(*, config: dict[str, object], database: str) -> None:
    """Deliver every stored Recall row a second time, as a retried insert would."""

    execute_clickhouse_sql(
        config=config,
        statements=tuple(
            f"INSERT INTO {database}.{table} SETTINGS insert_deduplicate = 0 "
            f"SELECT * FROM {database}.{table}"
            for table in RECALL_TABLES
        ),
    )


def write_recall_project(
    *,
    parent: Path,
    config: dict[str, object],
    database: str,
    settings: tuple[str, str] = ("", ""),
    targets: int = 1,
) -> Path:
    """Write the local Recall test project, sending its history to `database`."""

    recall_settings, connection_settings = settings
    return write_project(
        parent / "orders_shop",
        extra_toml=recall_store_toml(
            config=config,
            database=database,
            recall_settings=recall_settings,
            connection_settings=connection_settings,
        ),
        targets=targets,
    )
