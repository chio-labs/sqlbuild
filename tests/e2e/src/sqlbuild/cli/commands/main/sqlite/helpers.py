"""Helpers for SQLite CLI e2e tests."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType
from typing import Any

from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import query_duckdb

SQLITE_FILE: str = "warehouse.sqlite"
DUCKDB_FILE: str = "warehouse.duckdb"
SCHEMA: str = "analytics"

_CUSTOMERS_CSV: str = (
    "customer_id,customer_name,is_active,signed_up_at\n"
    "1,Ada,true,2026-01-01 08:00:00\n"
    "2,Grace,false,2026-01-02 09:30:00\n"
    "3,Linus,true,2026-01-03 10:15:00\n"
)
_ORDER_ROWS: tuple[str, ...] = (
    "1,10,1,1250,2026-01-05 10:00:00,placed",
    "2,11,1,725,2026-01-06 11:00:00,shipped",
    "3,12,2,3000,2026-01-06 12:00:00,placed",
    "4,13,3,500,2026-01-07 13:00:00,placed",
)
LATE_ORDER_ROWS: tuple[str, ...] = (
    "5,12,2,3100,2026-01-06 12:00:00,shipped",
    "6,14,3,900,2026-01-08 09:00:00,placed",
)

_SEEDS_YML: str = """seeds:
  - name: customers
    description: Customer list.
    columns:
      - name: customer_id
        type: INTEGER
      - name: customer_name
        type: VARCHAR
      - name: is_active
        type: BOOLEAN
      - name: signed_up_at
        type: VARCHAR
  - name: orders
    description: Order events; a later row for an order replaces earlier ones.
    columns:
      - name: event_seq
        type: INTEGER
      - name: order_id
        type: INTEGER
      - name: customer_id
        type: INTEGER
      - name: amount_cents
        type: INTEGER
      - name: ordered_at
        type: VARCHAR
      - name: status
        type: VARCHAR
"""

_MODELS: dict[str, str] = {
    "models/staging/stg_orders.sql": """MODEL (
  materialized view,
  description "Latest event per order.",
  columns (
    order_id (audits [not_null, unique]),
  ),
);

SELECT order_id, customer_id, amount_cents, ordered_at, status
FROM (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY event_seq DESC) AS event_rank
  FROM __seed("orders")
) AS ranked
WHERE event_rank = 1
""",
    "models/marts/customer_totals.sql": """MODEL (
  materialized table,
  description "Order totals per customer.",
  columns (
    customer_id (audits [not_null, unique]),
  ),
);

SELECT c.customer_id, c.customer_name, COUNT(o.order_id) AS order_count,
  COALESCE(SUM(o.amount_cents), 0) AS total_cents
FROM __seed("customers") AS c
LEFT JOIN __ref("stg_orders") AS o ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
""",
    "models/marts/orders_appended.sql": """MODEL (
  materialized incremental,
  incremental_strategy append,
  cursor order_id,
  cursor_type integer,
  description "Append-only order ids.",
);

SELECT order_id, customer_id FROM __ref("stg_orders")
""",
    "models/marts/orders_merged.sql": """MODEL (
  materialized incremental,
  incremental_strategy merge,
  unique_key [order_id],
  description "Current order status, merged by key.",
);

SELECT order_id, status, amount_cents FROM __ref("stg_orders")
""",
    "models/marts/orders_replaced.sql": """MODEL (
  materialized incremental,
  incremental_strategy delete_insert,
  unique_key [order_id],
  description "Current order status, replaced by key.",
);

SELECT order_id, status, amount_cents FROM __ref("stg_orders")
""",
}

_UNIT_TEST: str = """TEST();

WITH
__seed__customers AS (
  SELECT 1 AS customer_id, 'Ada' AS customer_name, 1 AS is_active, '2026-01-01' AS signed_up_at
),
__ref__stg_orders AS (
  SELECT 10 AS order_id, 1 AS customer_id, 250 AS amount_cents,
    '2026-01-05' AS ordered_at, 'placed' AS status
),
__expected__customer_totals AS (
  SELECT 1 AS customer_id, 'Ada' AS customer_name, 1 AS order_count, 250 AS total_cents
)
SELECT 1
"""

COMPARED_MODELS: tuple[tuple[str, str], ...] = (
    ("stg_orders", "order_id"),
    ("customer_totals", "customer_id"),
    ("orders_appended", "order_id"),
    ("orders_merged", "order_id"),
    ("orders_replaced", "order_id"),
)


def build_orders_project_files(*, adapter: str) -> dict[str, str]:
    """Build a synthetic orders project for one adapter, written in portable SQL."""

    connection: str = _CONNECTIONS[adapter]
    return {
        "sqlbuild_project.toml": (
            'name = "orders_shop"\n'
            f'adapter = "{adapter}"\n'
            'default_target = "dev"\n\n'
            f"[connection]\n{connection}\n"
            "[targets.dev]\n"
            f'schema = "{SCHEMA}"\n\n'
            "[targets.dev.clone]\n"
            "allow_as_clone_origin = true\n\n"
            "[targets.prod]\n"
            'schema = "prod"\n\n'
            "[targets.prod.clone]\n"
            "allow_as_clone_destination = true\n\n"
            "[defaults]\n"
            'materialized = "table"\n'
        ),
        "seeds/customers.csv": _CUSTOMERS_CSV,
        "seeds/orders.csv": "event_seq,order_id,customer_id,amount_cents,ordered_at,status\n"
        + "\n".join(_ORDER_ROWS)
        + "\n",
        "seeds/seeds.yml": _SEEDS_YML,
        "tests/unit/test_customer_totals.sql": _UNIT_TEST,
        **_MODELS,
    }


def append_late_orders(*, project_dir: Path) -> None:
    orders_path: Path = project_dir / "seeds" / "orders.csv"
    with orders_path.open("a", encoding="utf-8") as orders_file:
        orders_file.write("\n".join(LATE_ORDER_ROWS) + "\n")


def sqlite_rows(*, db_path: Path, sql: str) -> tuple[tuple[object, ...], ...]:
    connection: sqlite3.Connection = sqlite3.connect(db_path)
    try:
        return tuple(tuple(row) for row in connection.execute(sql).fetchall())
    finally:
        connection.close()


def model_rows(
    *, adapter: str, project_dir: Path, model: str, order_by: str
) -> tuple[tuple[object, ...], ...]:
    """Read one model's rows in a stable order from either engine."""

    return _ROW_READERS[adapter](project_dir, model, order_by)


def _sqlite_model_rows(
    project_dir: Path, model: str, order_by: str
) -> tuple[tuple[object, ...], ...]:
    return sqlite_rows(
        db_path=project_dir / SQLITE_FILE,
        sql=f'SELECT * FROM "{SCHEMA}__{model}" ORDER BY {order_by}',
    )


def _duckdb_model_rows(
    project_dir: Path, model: str, order_by: str
) -> tuple[tuple[object, ...], ...]:
    return tuple(
        tuple(row)
        for row in query_duckdb(
            db_path=project_dir / DUCKDB_FILE,
            sql=f"SELECT * FROM {SCHEMA}.{model} ORDER BY {order_by}",
        )
    )


_CONNECTIONS: MappingProxyType[str, str] = MappingProxyType(
    {"sqlite": f'path = "{SQLITE_FILE}"\n', "duckdb": f'database = "{DUCKDB_FILE}"\n'}
)
_ROW_READERS: MappingProxyType[str, Callable[[Path, str, str], tuple[tuple[object, ...], ...]]] = (
    MappingProxyType({"sqlite": _sqlite_model_rows, "duckdb": _duckdb_model_rows})
)


_EVENTS_HEADER: str = "order_id,amount_cents,ordered_at\n"
FIRST_EVENTS_CSV: str = _EVENTS_HEADER + (
    "1,100,2026-01-01 10:00:00\n2,200,2026-01-01 11:00:00\n3,300,2026-01-02 09:00:00\n"
)
CHANGED_EVENTS_CSV: str = _EVENTS_HEADER + (
    "2,250,2026-01-02 12:00:00\n3,300,2026-01-02 09:00:00\n4,400,2026-01-03 08:00:00\n"
)

_SQLITE_TOML: str = (
    'name = "events_shop"\n'
    'adapter = "sqlite"\n'
    'default_target = "dev"\n\n'
    "[connection]\n"
    f'path = "{SQLITE_FILE}"\n\n'
    "[targets.dev]\n"
    f'schema = "{SCHEMA}"\n'
)

STRATEGY_PROJECT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": _SQLITE_TOML,
    "seeds/order_events.csv": FIRST_EVENTS_CSV,
    "seeds/seeds.yml": """seeds:
  - name: order_events
    description: Order events.
    columns:
      - name: order_id
        type: INTEGER
      - name: amount_cents
        type: INTEGER
      - name: ordered_at
        type: TIMESTAMP
""",
    "models/daily_revenue.sql": """MODEL (
  description "Daily revenue in sequential microbatches.",
  materialized incremental,
  incremental_strategy delete_insert,
  incremental_mode microbatch,
  microbatch_strategy watermark,
  cursor_watermark_mode all,
  cursor order_day,
  cursor_type timestamp,
  cursor_grain day,
  cursor_inputs (order_events (column ordered_at, roles [filter, watermark]),),
  batch_size 1d,
);

SELECT datetime(ordered_at, 'start of day') AS order_day, COUNT(*) AS order_count,
  SUM(amount_cents) AS revenue_cents
FROM __seed("order_events")
WHERE ordered_at >= __cursor_start() AND ordered_at < __cursor_end()
GROUP BY 1
""",
    "models/orders_window.sql": """MODEL (
  description "Orders replaced by daily cursor window.",
  materialized incremental,
  incremental_strategy delete_insert,
  unique_key order_id,
  cursor ordered_at,
  cursor_type timestamp,
  cursor_grain day,
  cursor_start "2026-01-01",
);

SELECT order_id, amount_cents, ordered_at FROM __seed("order_events")
""",
    "models/current_orders.sql": """MODEL (description "Current order state.", materialized table);

SELECT order_id, amount_cents, ordered_at AS updated_at FROM __seed("order_events")
""",
    "models/order_history.sql": """MODEL (
  description "Order history by update time.",
  materialized snapshot,
  unique_key [order_id],
  snapshot_strategy timestamp,
  updated_at updated_at,
  invalidate_hard_deletes true,
);

SELECT order_id, amount_cents, updated_at FROM __ref("current_orders")
""",
    "models/order_amount_history.sql": """MODEL (
  description "Order amount history by checked columns.",
  materialized snapshot,
  unique_key [order_id],
  snapshot_strategy check,
  check_columns [amount_cents],
);

SELECT order_id, amount_cents FROM __ref("current_orders")
""",
}

CONTRACT_PROJECT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": _SQLITE_TOML,
    "models/order_amounts.sql": """MODEL (
  description "Order amounts with an exact decimal contract.",
  contract enforced,
  columns (
    order_id (type INTEGER, nullable false),
    amount (type DECIMAL(10,2)),
  ),
);

SELECT 1 AS order_id, 12.5 AS amount
UNION ALL SELECT 2, 7
""",
}

FUNCTION_PROJECT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": _SQLITE_TOML,
    "functions/sql/is_large.sql": """FUNCTION (
  description "Whether an amount is large.",
  arguments (amount INTEGER),
  returns BOOLEAN,
);

amount > 10
""",
    "models/large_orders.sql": """MODEL (description "Large orders.", materialized table);

SELECT 1 AS order_id
""",
}

CONCURRENT_MICROBATCH_PROJECT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": _SQLITE_TOML + "\n[settings]\nmicrobatch_concurrency = true\n",
    "seeds/order_events.csv": FIRST_EVENTS_CSV,
    "seeds/seeds.yml": STRATEGY_PROJECT_FILES["seeds/seeds.yml"],
    "models/daily_revenue.sql": STRATEGY_PROJECT_FILES["models/daily_revenue.sql"].replace(
        "  batch_size 1d,\n", "  batch_size 1d,\n  batch_concurrency 4,\n"
    ),
}

LOCK_PROJECT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": _SQLITE_TOML.replace(
        f'path = "{SQLITE_FILE}"\n', f'path = "{SQLITE_FILE}"\nbusy_timeout = 0.5\n'
    ),
    "models/order_ids.sql": """MODEL (description "Order ids.", materialized table);

SELECT 1 AS order_id
""",
}


SCENARIO_PROJECT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": _SQLITE_TOML,
    "sources/raw.yml": """sources:
  - name: raw_orders
    description: Raw orders.
    schema: main
    table: raw_orders
    columns:
      - name: id
        type: INTEGER
      - name: customer_id
        type: INTEGER
      - name: amount
        type: INTEGER
      - name: ordered_at
        type: TIMESTAMP
""",
    "models/orders.sql": """MODEL (description 'Orders.', materialized table);

SELECT id AS order_id, customer_id, amount, ordered_at FROM __source("raw_orders")
""",
    "models/customer_totals.sql": """MODEL (description 'Totals per customer.', materialized table);

SELECT customer_id, SUM(amount) AS total_amount, COUNT(*) AS order_count
FROM __ref("orders")
GROUP BY customer_id
""",
    "models/daily_orders.sql": """MODEL (
  description 'Orders by day, incremental.',
  materialized incremental,
  incremental_strategy delete_insert,
  unique_key order_day,
  cursor order_day,
  cursor_type timestamp,
  cursor_grain day,
  cursor_start "2026-01-01",
);

SELECT date(ordered_at) AS order_day, COUNT(*) AS order_count
FROM __ref("orders")
GROUP BY 1
""",
    "tests/scenarios/customer_totals_pass.sql": """SCENARIO (description "Customer totals.");

WITH
__source__raw_orders AS (
  SELECT 1 AS id, 10 AS customer_id, 10 AS amount, '2026-01-01 10:00:00' AS ordered_at
  UNION ALL
  SELECT 2, 10, 5, '2026-01-02 10:00:00'
  UNION ALL
  SELECT 3, 20, 7, '2026-01-02 11:00:00'
),
__expected__customer_totals AS (
  SELECT 10 AS customer_id, 15 AS total_amount, 2 AS order_count
  UNION ALL
  SELECT 20, 7, 1
),
__expected__daily_orders AS (
  SELECT '2026-01-01' AS order_day, 1 AS order_count
  UNION ALL
  SELECT '2026-01-02', 2
)
SELECT 1
""",
    "tests/scenarios/customer_totals_fail.sql": """SCENARIO (description 'Wrong totals.');

WITH
__source__raw_orders AS (
  SELECT 1 AS id, 10 AS customer_id, 10 AS amount, '2026-01-01 10:00:00' AS ordered_at
),
__expected__customer_totals AS (
  SELECT 10 AS customer_id, 11 AS total_amount, 1 AS order_count
)
SELECT 1
""",
    "tests/scenarios/nested/orders_assert_pass.sql": """SCENARIO (description 'No negatives.');

WITH
__source__raw_orders AS (
  SELECT 1 AS id, 10 AS customer_id, 10 AS amount, '2026-01-01 10:00:00' AS ordered_at
),
__assert__no_negative_orders AS (
  SELECT * FROM __ref("orders") WHERE amount < 0
)
SELECT 1
""",
    "tests/scenarios/orders_assert_fail.sql": """SCENARIO (description 'Every order is large.');

WITH
__source__raw_orders AS (
  SELECT 1 AS id, 10 AS customer_id, 3 AS amount, '2026-01-01 10:00:00' AS ordered_at
),
__assert__small_orders AS (
  SELECT * FROM __ref("orders") WHERE amount < 5
)
SELECT 1
""",
}

SCENARIO_OUTCOMES: dict[str, tuple[str, str | None]] = {
    "customer_totals_pass": ("success", None),
    "customer_totals_fail": ("failed", "X506"),
    "orders_assert_pass": ("success", None),
    "orders_assert_fail": ("failed", "X508"),
}


def scenario_outcomes(payload: dict[str, Any]) -> dict[str, tuple[str, str | None]]:
    return {
        str(scenario["name"]): (str(scenario["status"]), scenario.get("error_code"))
        for scenario in payload["scenarios"]
    }


def scenario_table_shapes(*, db_path: Path) -> tuple[str, ...]:
    """Table names with each scenario run identifier replaced, sorted."""

    return tuple(
        sorted(
            re.sub(r"__sqb_[0-9a-f]+__", "__sqb_<run>__", name)
            for name in table_names(db_path=db_path)
        )
    )


def table_names(*, db_path: Path) -> tuple[str, ...]:
    return tuple(
        str(row[0])
        for row in sqlite_rows(
            db_path=db_path, sql="SELECT name FROM sqlite_schema WHERE type = 'table'"
        )
    )


def hold_sqlite_write_lock(*, db_path: str, ready_path: str, hold_seconds: float) -> None:
    """Child process: hold the file's write lock while a CLI writer tries to build."""

    import time

    connection: sqlite3.Connection = sqlite3.connect(db_path, isolation_level=None)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("BEGIN IMMEDIATE")
    connection.execute("CREATE TABLE IF NOT EXISTS lock_holder (held INTEGER)")
    Path(ready_path).write_text("ready", encoding="utf-8")
    time.sleep(hold_seconds)
    connection.execute("COMMIT")
    connection.close()


def execute_sqlite(*, db_path: Path, sql: str) -> None:
    connection: sqlite3.Connection = sqlite3.connect(db_path)
    try:
        connection.execute(sql)
        connection.commit()
    finally:
        connection.close()
