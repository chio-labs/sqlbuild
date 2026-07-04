"""Databricks E2E tests for declarative dlt source loading."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.databricks._test_types import (
    DatabricksDltE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.databricks.helpers import (
    build_databricks_project_toml,
    build_unique_schema_name,
    cleanup_databricks_schema,
    ensure_databricks_schema_ready,
    fetch_databricks_rows,
    relation_name,
)
from tests.e2e.src.sqlbuild.cli.commands.main.load.helpers import (
    write_sqlite_orders_source_database,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DatabricksDltE2ETestCase(
            description="loads sqlite dlt source into databricks raw schema",
            expected_loaded_rows=((1, 10), (2, 20), (3, 30)),
            expected_model_rows=((2, 20), (3, 30)),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_dlt_source_when_loading_to_databricks_then_table_is_materialized_and_queryable(
    tmp_path: Path,
    test_case: DatabricksDltE2ETestCase,
) -> None:
    schema_base: str = build_unique_schema_name(prefix="sqb_dlt_databricks")
    model_schema_name: str = f"{schema_base}_models"
    raw_schema_name: str = f"{schema_base}_raw"
    project_name: str = "dlt_databricks_project"
    source_db_path: Path = tmp_path / project_name / "source.db"
    try:
        ensure_databricks_schema_ready(schema_name=model_schema_name)
        ensure_databricks_schema_ready(schema_name=raw_schema_name)
        project_dir: Path = prepare_inline_project(
            tmp_path=tmp_path,
            project_name=project_name,
            repo_files={
                "sqlbuild_project.toml": build_databricks_project_toml(
                    project_name=project_name,
                    schema_name=model_schema_name,
                ),
                "sources/raw.yml": (
                    "dlt_sources:\n"
                    "  - type: sql_database\n"
                    f"    schema: {raw_schema_name}\n"
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

        assert load_result.returncode == test_case.expected_return_code, (
            load_result.stdout + load_result.stderr
        )
        loaded_rows: tuple[tuple[object, ...], ...] = fetch_databricks_rows(
            schema_name=raw_schema_name,
            sql=(
                "SELECT order_id, amount FROM "
                f"{relation_name(schema_name=raw_schema_name, name='raw_orders')} "
                "ORDER BY order_id"
            ),
        )
        assert loaded_rows == test_case.expected_loaded_rows

        build_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build", "--select", "order_totals"),
            project_dir=project_dir,
        )

        assert build_result.returncode == test_case.expected_return_code, (
            build_result.stdout + build_result.stderr
        )
        model_rows: tuple[tuple[object, ...], ...] = fetch_databricks_rows(
            schema_name=model_schema_name,
            sql=(
                "SELECT order_id, amount FROM "
                f"{relation_name(schema_name=model_schema_name, name='order_totals')} "
                "ORDER BY order_id"
            ),
        )
        assert model_rows == test_case.expected_model_rows
    finally:
        cleanup_databricks_schema(schema_name=raw_schema_name)
        cleanup_databricks_schema(schema_name=model_schema_name)
