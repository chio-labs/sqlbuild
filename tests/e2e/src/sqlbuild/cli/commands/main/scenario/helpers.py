"""Helpers for sqb scenario command e2e tests."""

from __future__ import annotations

from pathlib import Path

from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import query_duckdb


def build_scenario_project_files() -> dict[str, str]:
    """Build an inline project with passing and failing SQL scenarios."""

    return {
        "sqlbuild_project.toml": (
            'name = "scenario_demo"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "scenario_demo.duckdb"\n\n'
            "[defaults]\n"
            'materialized = "table"\n'
        ),
        "sources/raw.yml": (
            "sources:\n  - name: raw_orders\n    schema: main\n    table: raw_orders\n"
        ),
        "models/orders.sql": (
            "MODEL (materialized table);\n\n"
            "SELECT\n"
            "  id AS order_id,\n"
            "  amount\n"
            'FROM __source("raw_orders")\n'
        ),
        "models/order_totals.sql": (
            "MODEL (materialized table);\n\n"
            "SELECT\n"
            "  SUM(amount) AS total_amount\n"
            'FROM __ref("orders")\n'
        ),
        "tests/scenarios/order_totals_pass.sql": (
            'SCENARIO (description: "Order totals scenario", tags: ["scenario"]);\n\n'
            "WITH\n"
            "__source__raw_orders AS (\n"
            "  SELECT 1 AS id, 10 AS amount\n"
            "  UNION ALL\n"
            "  SELECT 2 AS id, 5 AS amount\n"
            "),\n"
            "__expected__order_totals AS (\n"
            "  SELECT 15 AS total_amount\n"
            ")\n"
            "SELECT 1\n"
        ),
        "tests/scenarios/nested/orders_assert_pass.sql": (
            "SCENARIO ();\n\n"
            "WITH\n"
            "__source__raw_orders AS (\n"
            "  SELECT 1 AS id, 10 AS amount\n"
            "),\n"
            "__assert__no_negative_orders AS (\n"
            '  SELECT * FROM __ref("orders") WHERE amount < 0\n'
            ")\n"
            "SELECT 1\n"
        ),
        "tests/scenarios/order_totals_fail.sql": (
            "SCENARIO ();\n\n"
            "WITH\n"
            "__source__raw_orders AS (\n"
            "  SELECT 1 AS id, 10 AS amount\n"
            "),\n"
            "__expected__order_totals AS (\n"
            "  SELECT 11 AS total_amount\n"
            ")\n"
            "SELECT 1\n"
        ),
    }


def list_scenario_relation_names(*, db_path: Path) -> tuple[str, ...]:
    """Return DuckDB relation names owned by scenario artifact prefixes."""

    rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_name LIKE '__sqb_%' "
            "ORDER BY table_name"
        ),
    )
    return tuple(str(row[0]) for row in rows)
