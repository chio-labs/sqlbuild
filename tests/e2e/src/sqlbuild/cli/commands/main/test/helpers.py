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
        "tests/test_chain.sql": (
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
