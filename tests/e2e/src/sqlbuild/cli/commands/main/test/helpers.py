"""Helpers for sqb test command e2e tests."""

from __future__ import annotations


def build_chain_test_project_files(*, sqlglot_enabled: bool) -> dict[str, str]:
    """Build an inline project with a two-model SQL unit-test chain."""

    sqlglot_value: str = "true" if sqlglot_enabled else "false"
    return {
        "sqlbuild_project.toml": (
            'name = "demo"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "demo.duckdb"\n\n'
            "[settings]\n"
            f"sqlglot = {sqlglot_value}\n"
        ),
        "models/stg_orders.sql": (
            "MODEL (materialized table);\n\n"
            "SELECT\n"
            "  id,\n"
            "  @mocked_amount() AS amount,\n"
            "  @mocked_country() AS country,\n"
            "  @mocked_literal_text() AS literal_text,\n"
            "  @real_status() AS status\n"
            'FROM __source("raw")'
        ),
        "models/fact_orders.sql": (
            "MODEL (materialized table);\n\n"
            "SELECT\n"
            "  id,\n"
            "  amount + 1 AS adjusted,\n"
            "  country,\n"
            "  literal_text,\n"
            "  status\n"
            'FROM __ref("stg_orders")'
        ),
        "macros/test_macros.py": (
            "def mocked_amount() -> str:\n"
            '    return "0"\n\n'
            "def mocked_country() -> str:\n"
            "    return \"'CA'\"\n\n"
            "def mocked_literal_text() -> str:\n"
            "    return \"'real'\"\n\n"
            "def real_status() -> str:\n"
            "    return \"'active'\"\n"
        ),
        "sources/raw.yml": "sources:\n  - name: raw\n    schema: main\n    table: raw\n",
        "tests/unit/test_chain.sql": (
            "TEST();\n\n"
            "WITH\n"
            "__macro__mocked_amount AS (SELECT '100'),\n"
            "__macro__mocked_country AS (SELECT '''US'''),\n"
            "__macro__mocked_literal_text AS (SELECT ''' + x + '''),\n"
            "__source__raw AS (SELECT 1 AS id),\n"
            "__expected__stg_orders AS (\n"
            "  SELECT 1 AS id, 100 AS amount, 'US' AS country, ' + x + ' AS literal_text, "
            "'active' AS status\n"
            "),\n"
            "__expected__fact_orders AS (\n"
            "  SELECT 1 AS id, 101 AS adjusted, 'US' AS country, ' + x + ' AS "
            "literal_text, 'active' AS status\n"
            ")\n"
            "SELECT 1\n"
        ),
    }


def build_assertion_test_project_files(*, failing: bool) -> dict[str, str]:
    """Build an inline project with a SQL unit-test zero-row assertion."""

    amount: int = -10 if failing else 10
    return {
        "sqlbuild_project.toml": (
            'name = "assertion_demo"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "assertion_demo.duckdb"\n\n'
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
        "tests/unit/orders_assert.sql": (
            "TEST();\n\n"
            "WITH\n"
            f"__source__raw_orders AS (SELECT 1 AS id, {amount} AS amount),\n"
            "__assert__no_negative_orders AS (\n"
            '  SELECT * FROM __ref("orders") WHERE amount < 0\n'
            ")\n"
            "SELECT 1\n"
        ),
    }


def build_macro_test_project_files() -> dict[str, str]:
    """Build an inline project with a macro unit test guarding one model."""

    return {
        "sqlbuild_project.toml": (
            'name = "macro_test_demo"\n'
            'adapter = "duckdb"\n\n'
            "[connection]\n"
            'database = "macro_test_demo.duckdb"\n\n'
            "[defaults]\n"
            'materialized = "table"\n'
        ),
        "macros/status.py": (
            'def normalize_status(value: str) -> str:\n    return f"LOWER(TRIM({value}))"\n'
        ),
        "models/orders.sql": (
            "MODEL (materialized table);\n\nSELECT @normalize_status(\"'  PAID  '\") AS status\n"
        ),
        "tests/unit/test_normalize_status.sql": (
            'TEST (mode: macro, name: "normalizes status");\n\n'
            "WITH\n"
            "input_values AS (SELECT '  PAID  ' AS raw_status),\n"
            "__macro_actual__ AS (\n"
            '  SELECT @normalize_status("raw_status") AS status FROM input_values\n'
            "),\n"
            "__macro_expected__ AS (SELECT 'paid' AS status)\n"
            "SELECT 1\n"
        ),
    }
