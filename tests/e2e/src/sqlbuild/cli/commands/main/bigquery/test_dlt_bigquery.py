"""BigQuery E2E tests for declarative dlt source loading."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.bigquery._test_types import (
    BigQueryDltE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.bigquery.helpers import (
    build_bigquery_project_toml,
    build_unique_dataset_name,
    cleanup_bigquery_dataset,
    ensure_bigquery_dataset_ready,
    fetch_bigquery_rows,
    relation_name,
)
from tests.e2e.src.sqlbuild.cli.commands.main.load.helpers import (
    write_sqlite_orders_source_database,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryDltE2ETestCase(
            description="loads sqlite dlt source into bigquery raw dataset",
            expected_loaded_rows=((1, 10), (2, 20), (3, 30)),
            expected_model_rows=((2, 20), (3, 30)),
        )
    ],
    ids=["loads sqlite dlt source into bigquery raw dataset"],
)
def test_given_dlt_source_when_loading_to_bigquery_then_table_is_materialized_and_queryable(
    tmp_path: Path,
    test_case: BigQueryDltE2ETestCase,
) -> None:
    dataset_base: str = build_unique_dataset_name(prefix="sqb_dlt_bigquery")
    model_dataset_name: str = f"{dataset_base}_models"
    raw_dataset_name: str = f"{dataset_base}_raw"
    project_name: str = "dlt_bigquery_project"
    source_db_path: Path = tmp_path / project_name / "source.db"
    try:
        ensure_bigquery_dataset_ready(dataset_name=model_dataset_name)
        ensure_bigquery_dataset_ready(dataset_name=raw_dataset_name)
        project_dir: Path = prepare_inline_project(
            tmp_path=tmp_path,
            project_name=project_name,
            repo_files={
                "sqlbuild_project.toml": build_bigquery_project_toml(
                    project_name=project_name,
                    dataset_name=model_dataset_name,
                ),
                "sources/raw.yml": (
                    "dlt_sources:\n"
                    "  - type: sql_database\n"
                    f"    schema: {raw_dataset_name}\n"
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
        loaded_rows: tuple[tuple[object, ...], ...] = fetch_bigquery_rows(
            dataset_name=raw_dataset_name,
            sql=(
                "SELECT order_id, amount FROM "
                f"{relation_name(dataset_name=raw_dataset_name, name='raw_orders')} "
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
        model_rows: tuple[tuple[object, ...], ...] = fetch_bigquery_rows(
            dataset_name=model_dataset_name,
            sql=(
                "SELECT order_id, amount FROM "
                f"{relation_name(dataset_name=model_dataset_name, name='order_totals')} "
                "ORDER BY order_id"
            ),
        )
        assert model_rows == test_case.expected_model_rows
    finally:
        cleanup_bigquery_dataset(dataset_name=raw_dataset_name)
        cleanup_bigquery_dataset(dataset_name=model_dataset_name)
