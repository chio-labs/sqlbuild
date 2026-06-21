"""E2E tests for declarative dlt source loading."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.load._test_types import DltSqlDatabaseE2ETestCase
from tests.e2e.src.sqlbuild.cli.commands.main.load.helpers import (
    write_sqlite_orders_source_database,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DltSqlDatabaseE2ETestCase(
            description="loads sqlite sql_database source into duckdb",
            expected_loaded_rows=((1, 10), (2, 20), (3, 30)),
            expected_model_rows=((2, 20), (3, 30)),
        )
    ],
    ids=["loads sqlite sql_database source into duckdb"],
)
def test_given_dlt_sql_database_source_when_loading_then_table_is_materialized_and_queryable(
    tmp_path: Path, test_case: DltSqlDatabaseE2ETestCase
) -> None:
    project_name: str = "dlt_sql_database_project"
    warehouse_db_path: Path = tmp_path / project_name / "warehouse.duckdb"
    source_db_path: Path = tmp_path / project_name / "source.db"
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            "sqlbuild_project.toml": (
                'name = "dlt_sql_database_project"\n'
                'adapter = "duckdb"\n\n'
                "[connection]\n"
                f'database = "{warehouse_db_path}"\n\n'
                "[defaults]\n"
                'materialized = "table"\n'
            ),
            "sources/raw.yml": (
                "dlt_sources:\n"
                "  - type: sql_database\n"
                "    config:\n"
                f'      credentials: "sqlite:///{source_db_path}"\n'
                "    resources:\n"
                "      - name: raw_orders\n"
                "        table: orders\n"
                "        write_disposition: replace\n"
            ),
            "models/order_totals.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT order_id, amount FROM __source("raw_orders") WHERE amount >= 20\n'
            ),
        },
    )
    write_sqlite_orders_source_database(source_db_path)

    load_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "load", "--select", "raw_orders"),
        project_dir=project_dir,
    )

    assert load_result.returncode == 0, load_result.stdout + load_result.stderr
    loaded_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=warehouse_db_path,
        sql="SELECT order_id, amount FROM raw_orders ORDER BY order_id",
    )
    assert tuple(loaded_rows) == test_case.expected_loaded_rows

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "order_totals"),
        project_dir=project_dir,
    )

    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    model_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=warehouse_db_path,
        sql="SELECT order_id, amount FROM order_totals ORDER BY order_id",
    )
    assert tuple(model_rows) == test_case.expected_model_rows
