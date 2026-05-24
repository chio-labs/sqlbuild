from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.integrations.ingestr._test_types import IngestrE2ETestCase
from tests.e2e.src.sqlbuild.integrations.ingestr.helpers import (
    duckdb_project_toml,
    execute_postgres_sql,
    fetch_duckdb_rows,
    fetch_postgres_rows,
    postgres_project_toml,
    postgres_uri,
    run_sqb_with_ingestr,
    write_project_files,
)


@pytest.mark.parametrize(
    "test_case",
    [
        IngestrE2ETestCase(
            description="loads postgres source into duckdb destination",
            expected_rows=((1, "postgres-source"), (2, "postgres-source")),
            expected_stdout_fragments=("ingestr execution", "raw_pg_orders", "OK"),
        )
    ],
    ids=["loads postgres source into duckdb destination"],
)
def test_given_postgres_source_when_loading_with_ingestr_then_duckdb_target_has_rows(
    tmp_path: Path,
    test_case: IngestrE2ETestCase,
    postgres_config: dict[str, object],
) -> None:
    source_table: str = "ingestr_pg_source_orders"
    execute_postgres_sql(
        config=postgres_config,
        sql=(
            f"DROP TABLE IF EXISTS public.{source_table}; "
            f"CREATE TABLE public.{source_table} (order_id INTEGER, status TEXT); "
            f"INSERT INTO public.{source_table} VALUES "
            "(1, 'postgres-source'), (2, 'postgres-source')"
        ),
    )
    project_dir: Path = tmp_path / "pg_to_duckdb"
    duckdb_path: Path = project_dir / "target.duckdb"
    write_project_files(
        project_dir=project_dir,
        files={
            "sqlbuild_project.toml": duckdb_project_toml(
                project_name="pg_to_duckdb", database_path=duckdb_path
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_pg_orders\n"
                "    ingestr:\n"
                f'      source_uri: "{postgres_uri(postgres_config)}"\n'
                f"      source_table: public.{source_table}\n"
            ),
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb_with_ingestr(
        command=("--no-color", "load"), project_dir=project_dir
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    assert (
        fetch_duckdb_rows(
            database_path=duckdb_path,
            sql="SELECT order_id, status FROM raw_pg_orders ORDER BY order_id",
        )
        == test_case.expected_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        IngestrE2ETestCase(
            description="build loads postgres source with ingestr before building model",
            expected_rows=((1, "new"), (2, "paid")),
            expected_stdout_fragments=("ingestr execution", "raw_pg_orders", "stg_pg_orders"),
        )
    ],
    ids=["build loads postgres source with ingestr before building model"],
)
def test_given_ingestr_source_when_building_with_load_then_model_reads_loaded_source(
    tmp_path: Path,
    test_case: IngestrE2ETestCase,
    postgres_config: dict[str, object],
) -> None:
    source_table: str = "orders_build_source"
    execute_postgres_sql(
        config=postgres_config,
        sql=f"DROP TABLE IF EXISTS public.{source_table}",
    )
    execute_postgres_sql(
        config=postgres_config,
        sql=f"CREATE TABLE public.{source_table} (order_id INTEGER, status TEXT)",
    )
    execute_postgres_sql(
        config=postgres_config,
        sql=f"INSERT INTO public.{source_table} VALUES (1, 'new'), (2, 'paid')",
    )
    duckdb_path: Path = tmp_path / "build_ingestr.duckdb"
    project_dir: Path = tmp_path / "build_pg_to_duckdb"
    write_project_files(
        project_dir=project_dir,
        files={
            "sqlbuild_project.toml": duckdb_project_toml(
                project_name="build_pg_to_duckdb", database_path=duckdb_path
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_pg_orders\n"
                "    columns:\n"
                "      - name: order_id\n"
                "        type: INTEGER\n"
                "      - name: status\n"
                "        type: VARCHAR\n"
                "    ingestr:\n"
                f'      source_uri: "{postgres_uri(postgres_config)}"\n'
                f"      source_table: public.{source_table}\n"
            ),
            "models/stg_pg_orders.sql": """
MODEL (materialized table);

SELECT order_id, status FROM __source("raw_pg_orders")
""".strip()
            + "\n",
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb_with_ingestr(
        command=("--no-color", "build", "--load"), project_dir=project_dir
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    assert (
        fetch_duckdb_rows(
            database_path=duckdb_path,
            sql="SELECT order_id, status FROM stg_pg_orders ORDER BY order_id",
        )
        == test_case.expected_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        IngestrE2ETestCase(
            description="loads duckdb source into postgres destination",
            expected_rows=((7, "duckdb-source"), (8, "duckdb-source")),
            expected_stdout_fragments=("ingestr execution", "raw_duckdb_orders", "OK"),
        )
    ],
    ids=["loads duckdb source into postgres destination"],
)
def test_given_duckdb_source_when_loading_with_ingestr_then_postgres_target_has_rows(
    tmp_path: Path,
    test_case: IngestrE2ETestCase,
    postgres_config: dict[str, object],
) -> None:
    import duckdb

    source_duckdb_path: Path = tmp_path / "source.duckdb"
    source_connection: duckdb.DuckDBPyConnection = duckdb.connect(str(source_duckdb_path))
    try:
        source_connection.execute("CREATE TABLE source_orders (order_id INTEGER, status VARCHAR)")
        source_connection.execute(
            "INSERT INTO source_orders VALUES (7, 'duckdb-source'), (8, 'duckdb-source')"
        )
    finally:
        source_connection.close()
    target_schema: str = "ingestr_duckdb_to_pg"
    execute_postgres_sql(
        config=postgres_config,
        sql=f"DROP SCHEMA IF EXISTS {target_schema} CASCADE",
    )
    project_dir: Path = tmp_path / "duckdb_to_pg"
    write_project_files(
        project_dir=project_dir,
        files={
            "sqlbuild_project.toml": postgres_project_toml(
                project_name="duckdb_to_pg", config=postgres_config
            ),
            "sources/raw.yml": (
                "sources:\n"
                "  - name: raw_duckdb_orders\n"
                f"    schema: {target_schema}\n"
                "    ingestr:\n"
                f'      source_uri: "duckdb:///{source_duckdb_path}"\n'
                "      source_table: source_orders\n"
            ),
        },
    )

    try:
        result: subprocess.CompletedProcess[str] = run_sqb_with_ingestr(
            command=("--no-color", "load"), project_dir=project_dir
        )

        assert result.returncode == 0, result.stdout + result.stderr
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout
        assert (
            fetch_postgres_rows(
                config=postgres_config,
                sql=(
                    f"SELECT order_id, status FROM {target_schema}.raw_duckdb_orders "
                    "ORDER BY order_id"
                ),
            )
            == test_case.expected_rows
        )
    finally:
        execute_postgres_sql(
            config=postgres_config,
            sql=f"DROP SCHEMA IF EXISTS {target_schema} CASCADE",
        )
