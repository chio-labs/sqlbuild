"""E2E coverage for governed runtime-dynamic pivot columns."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    DynamicColumnContractE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    (
        DynamicColumnContractE2ETestCase(
            description="generated category columns are enforced",
            project_name="dynamic_category_amounts",
            expected_rows=((1, "10.25", "20.50"), (2, "7.00", None)),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_dynamic_pivot_contract_when_building_then_generated_columns_are_type_checked(
    test_case: DynamicColumnContractE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": (
                'name = "dynamic_category_amounts"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                'database = "warehouse.duckdb"\n\n'
                "[defaults]\n"
                'contract = "enforced"\n\n'
                "[rules]\n"
                'select = ["SQBRMODEL102", "SQBRCONTRACT101", "SQBRCONTRACT105", '
                '"SQBRCONTRACT106"]\n'
            ),
            "models/stg_order_amounts.sql": (
                "MODEL (\n"
                "  materialized table,\n"
                "  columns (\n"
                "    customer_id (type INTEGER),\n"
                "    category (type VARCHAR),\n"
                '    amount (type "DECIMAL(12,2)"),\n'
                "  ),\n"
                ");\n"
                "SELECT CAST(1 AS INTEGER) AS customer_id, "
                "CAST('books' AS VARCHAR) AS category, "
                "CAST(10.25 AS DECIMAL(12,2)) AS amount\n"
                "UNION ALL\n"
                "SELECT CAST(1 AS INTEGER), CAST('games' AS VARCHAR), "
                "CAST(20.50 AS DECIMAL(12,2))\n"
                "UNION ALL\n"
                "SELECT CAST(2 AS INTEGER), CAST('books' AS VARCHAR), "
                "CAST(7.00 AS DECIMAL(12,2))\n"
            ),
            "models/customer_category_amounts.sql": (
                "MODEL (\n"
                "  materialized table,\n"
                "  columns (customer_id (type INTEGER)),\n"
                "  dynamic_columns (\n"
                "    category_amounts (\n"
                "      pivot_column category,\n"
                "      value_column amount,\n"
                "      aggregate MAX,\n"
                '      type "DECIMAL(12,2)"\n'
                "    )\n"
                "  ),\n"
                ");\n"
                'PIVOT __ref("stg_order_amounts")\n'
                "ON category\n"
                "USING MAX(amount)\n"
                "GROUP BY customer_id\n"
            ),
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "SELECT customer_id, CAST(books AS VARCHAR), CAST(games AS VARCHAR) "
            "FROM main.customer_category_amounts ORDER BY customer_id"
        ),
    )

    assert tuple(rows) == test_case.expected_rows
