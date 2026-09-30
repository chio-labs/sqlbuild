"""Project builders and warehouse readers for `sqb rename` and `sqb mv` e2e tests."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)

DATABASE_FILE: str = "orders.duckdb"
SCHEMA: str = "analytics"
_PROJECT_TOML: str = (
    'name = "orders_project"\nadapter = "duckdb"\ndefault_target = "dev"\n\n'
    f'[connection]\ndatabase = "{DATABASE_FILE}"\n\n'
    f'[targets.dev]\nschema = "{SCHEMA}"\n\n'
    "[janitor]\nenabled = true\n"
)
_SOURCES_YML: str = (
    "sources:\n"
    "  - name: raw_orders\n"
    "    schema: main\n"
    "    table: raw_orders\n"
    "    columns:\n"
    "      - name: order_id\n"
    "      - name: customer_id\n"
    "      - name: amount\n"
    "      - name: order_date\n"
)
STG_ORDERS: str = (
    "MODEL (\n  materialized view,\n);\n\n"
    "SELECT\n  order_id,\n  customer_id,\n  amount,\n  order_date\n"
    'FROM __source("raw_orders")\n'
)
FACT_ORDERS: str = (
    "MODEL (\n  materialized table,\n);\n\n"
    "SELECT\n  o.order_id,\n  o.customer_id,\n  o.amount,\n  o.order_date\n"
    'FROM __ref("stg_orders") AS o\n'
)
CUSTOMER_TOTALS: str = (
    "MODEL (\n  materialized table,\n);\n\n"
    "SELECT\n  customer_id,\n  SUM(amount) AS total_amount\n"
    'FROM __ref("fact_orders")\nGROUP BY customer_id\n'
)
FACT_ORDERS_TEST: str = (
    "TEST();\n\n"
    "WITH\n"
    "__ref__stg_orders AS (\n"
    "  SELECT 1 AS order_id, 10 AS customer_id, 25 AS amount, "
    "CAST('2026-01-01' AS TIMESTAMP) AS order_date\n"
    "),\n"
    "__expected__fact_orders AS (\n"
    "  SELECT 1 AS order_id, 10 AS customer_id, 25 AS amount, "
    "CAST('2026-01-01' AS TIMESTAMP) AS order_date\n"
    ")\n"
    "SELECT 1\n"
)
BASE_FILES: dict[str, str] = {
    "sqlbuild_project.toml": _PROJECT_TOML,
    "sources/raw.yml": _SOURCES_YML,
    "models/staging/stg_orders.sql": STG_ORDERS,
    "models/marts/fact_orders.sql": FACT_ORDERS,
    "models/marts/customer_totals.sql": CUSTOMER_TOTALS,
    "tests/unit/test_fact_orders.sql": FACT_ORDERS_TEST,
}
UDF_FILE: tuple[str, str] = (
    "functions/sql/udf__is_large_order.sql",
    "FUNCTION (\n  arguments (amount INTEGER),\n  returns BOOLEAN,\n);\n\namount >= 100\n",
)
CENTS_MACRO: dict[str, str] = {
    "models/staging/_sqlbuild/_macros/cents.py": (
        'def to_cents(expression: str) -> str:\n    return f"({expression}) * 100"\n'
    ),
    "models/staging/stg_order_cents.sql": (
        "MODEL (\n  materialized view,\n);\n\n"
        'SELECT\n  order_id,\n  @to_cents("amount") AS amount_cents\nFROM __ref("stg_orders")\n'
    ),
}
ORDER_EXPORT: dict[str, str] = {
    "models/marts/order_export.sql": (
        'MODEL (\n  materialized view,\n);\n\nSELECT *\nFROM __ref("fact_orders")\n'
    ),
}
_INCREMENTAL_HEADER: str = (
    "  materialized incremental,\n"
    "  incremental_strategy delete_insert,\n"
    "  unique_key order_id,\n"
    "  cursor order_date,\n"
    "  cursor_type timestamp,\n"
    "  cursor_grain day,\n"
    '  cursor_start "2026-01-01",\n'
    "  cursor_inputs (\n    stg_orders order_date,\n  ),\n"
)


_HISTORY_HEADERS: dict[str, str] = {
    "table": "  materialized table,\n",
    "view": "  materialized view,\n",
    "incremental": _INCREMENTAL_HEADER,
}
_UDF_COLUMN: dict[bool, str] = {
    True: ',\n  __udf("udf__is_large_order")(amount) AS is_large',
    False: "",
}
_UDF_FILES: dict[bool, dict[str, str]] = {True: {UDF_FILE[0]: UDF_FILE[1]}, False: {}}


def order_history_files(*, materialized: str, udf: bool) -> dict[str, str]:
    """Return an order_history model, optionally calling a UDF discovery cannot fingerprint."""

    return {
        "models/marts/order_history.sql": (
            f"MODEL (\n{_HISTORY_HEADERS[materialized]});\n\n"
            f"SELECT\n  order_id,\n  amount,\n  order_date{_UDF_COLUMN[udf]}\n"
            'FROM __ref("stg_orders")\n'
        ),
        **_UDF_FILES[udf],
    }


def write_orders_project(
    *, tmp_path: Path, files: Mapping[str, str] | None = None, raw_order_count: int = 3
) -> Path:
    """Write the base orders project plus overrides and load raw orders."""

    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path, project_name="orders_project", repo_files={**BASE_FILES, **(files or {})}
    )
    load_raw_orders(project_dir=project_dir, order_ids=tuple(range(1, raw_order_count + 1)))
    return project_dir


def load_raw_orders(*, project_dir: Path, order_ids: tuple[int, ...]) -> None:
    """Replace the raw orders with one order per id, dated January of that day."""

    values: str = ", ".join(
        f"({order_id}, {10 + order_id % 2}, {order_id * 50}, TIMESTAMP '2026-01-{order_id:02d}')"
        for order_id in order_ids
    )
    execute_duckdb(
        db_path=project_dir / DATABASE_FILE,
        sql=(
            "CREATE OR REPLACE TABLE main.raw_orders AS SELECT * FROM (VALUES "
            f"{values}) AS t(order_id, customer_id, amount, order_date)"
        ),
    )


def sqb(project_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run one sqb command without colour."""

    return run_sqb(command=("--no-color", *args), project_dir=project_dir)


def sqb_json(project_dir: Path, *args: str) -> tuple[int, dict[str, Any]]:
    """Run one sqb command with --json and parse its stdout."""

    result: subprocess.CompletedProcess[str] = sqb(project_dir, *args, "--json")
    return result.returncode, json.loads(result.stdout)


def project_text(project_dir: Path) -> dict[str, str]:
    """Return every authored project file keyed by its relative path."""

    paths: tuple[Path, ...] = (
        project_dir / "sqlbuild_project.toml",
        *project_dir.glob("sources/*.yml"),
        *project_dir.glob("models/**/*.sql"),
        *project_dir.glob("models/**/*.py"),
        *project_dir.glob("functions/**/*.sql"),
        *project_dir.glob("tests/**/*.sql"),
    )
    return {
        path.relative_to(project_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(paths)
    }


def fragments_present(*, files: dict[str, str], expected: dict[str, tuple[str, ...]]) -> bool:
    """Return whether every expected fragment appears in its file."""

    found: list[bool] = []
    path: str
    fragments: tuple[str, ...]
    for path, fragments in expected.items():
        found.extend(fragment in files[path] for fragment in fragments)
    return all(found)


def relation_type(*, project_dir: Path, name: str) -> str | None:
    """Return the information_schema table type of one relation, or None."""

    rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=project_dir / DATABASE_FILE,
        sql=(
            "SELECT table_type FROM information_schema.tables "
            f"WHERE table_schema = '{SCHEMA}' AND table_name = '{name}'"
        ),
    )
    return next((str(row[0]) for row in rows), None)


def relation_columns(*, project_dir: Path, name: str) -> tuple[str, ...]:
    """Return the column names of one relation in ordinal order."""

    return tuple(
        str(row[0])
        for row in query_duckdb(
            db_path=project_dir / DATABASE_FILE,
            sql=(
                "SELECT column_name FROM information_schema.columns "
                f"WHERE table_schema = '{SCHEMA}' AND table_name = '{name}' "
                "ORDER BY ordinal_position"
            ),
        )
    )


def order_ids(*, project_dir: Path, name: str) -> tuple[int, ...]:
    """Return the order ids stored in one relation."""

    return tuple(
        int(row[0])
        for row in query_duckdb(
            db_path=project_dir / DATABASE_FILE,
            sql=f"SELECT order_id FROM {SCHEMA}.{name} ORDER BY order_id",
        )
    )
