from __future__ import annotations

from pathlib import Path

from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import prepare_inline_project


def prepare_freshness_project(*, tmp_path: Path) -> Path:
    return prepare_inline_project(
        tmp_path=tmp_path,
        project_name="freshness_command",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "freshness_command"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n'
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_orders\n"
                "    expression: SELECT 1 AS order_id\n"
                "    freshness:\n"
                "      strategy: sql\n"
                "      type: integer\n"
                "      query: SELECT 1 AS data_version\n"
                "  - name: raw_error\n"
                "    expression: SELECT 3 AS order_id\n"
                "    freshness:\n"
                "      strategy: sql\n"
                "      type: integer\n"
                "      query: SELECT missing_column AS data_version\n"
                "  - name: raw_unknown\n"
                "    expression: SELECT 2 AS order_id\n"
            ),
            "models/orders.sql": (
                'MODEL (materialized table);\n\nSELECT * FROM __source("raw_orders")\n'
            ),
        },
    )
