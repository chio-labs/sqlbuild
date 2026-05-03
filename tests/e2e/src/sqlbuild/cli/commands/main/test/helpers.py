"""Helpers for sqb test command e2e tests."""

from __future__ import annotations


def build_chain_test_project_files(*, sqlglot_enabled: bool) -> dict[str, str]:
    """Build an inline project with a two-model SQL unit-test chain."""

    sqlglot_value: str = "true" if sqlglot_enabled else "false"
    return {
        "sqlbuild_project.yml": (
            "name: demo\n"
            "adapter: duckdb\n"
            "connection:\n"
            "  database: demo.duckdb\n"
            "settings:\n"
            f"  sqlglot: {sqlglot_value}\n"
        ),
        "models/stg_orders.sql": (
            'MODEL (materialized table);\n\nSELECT id, amount FROM __source("raw")'
        ),
        "models/fact_orders.sql": (
            "MODEL (materialized table);\n\n"
            'SELECT id, amount + 1 AS adjusted FROM __ref("stg_orders")'
        ),
        "sources/raw.yml": "sources:\n  - name: raw\n    schema: main\n    table: raw\n",
        "tests/test_chain.sql": (
            "TEST();\n\n"
            "WITH\n"
            "__source__raw AS (SELECT 1 AS id, 100 AS amount),\n"
            "__expected__stg_orders AS (SELECT 1 AS id, 100 AS amount),\n"
            "__expected__fact_orders AS (SELECT 1 AS id, 101 AS adjusted)\n"
            "SELECT 1\n"
        ),
    }
