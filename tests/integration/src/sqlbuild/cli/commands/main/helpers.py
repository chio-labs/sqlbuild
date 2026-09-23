from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

import duckdb
import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main


def unavailable_artifact_directory(*, prefix: str) -> TemporaryDirectory[str]:
    raise OSError("temporary storage unavailable")


def write_compile_startup_project(project_dir: Path) -> None:
    """Write the minimal project used by fresh-process import tests."""

    (project_dir / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    models_dir: Path = project_dir / "models"
    models_dir.mkdir()
    (models_dir / "orders.sql").write_text(
        "MODEL (materialized table);\nSELECT 1 AS order_id\n", encoding="utf-8"
    )


def write_from_values_format_project(*, tmp_path: Path, adapter: str) -> tuple[Path, Path]:
    """Write a format project containing an authored values relation."""

    project_dir: Path = tmp_path / adapter
    project_dir.mkdir()
    (project_dir / "sqlbuild_project.toml").write_text(
        f'name = "orders"\nadapter = "{adapter}"\n\n[rules]\nselect = ["SQBRSQL039"]\n',
        encoding="utf-8",
    )
    models: Path = project_dir / "models"
    models.mkdir()
    (models / "customers.sql").write_text(
        'MODEL (description "Customers.");\nSELECT 1 AS customer_key\n', encoding="utf-8"
    )
    (models / "orders.sql").write_text(
        'MODEL (description "Orders.");\nSELECT customer_key, 1 AS order_count '
        'FROM __ref("customers")\n',
        encoding="utf-8",
    )
    test_file: Path = project_dir / "tests" / "unit" / "test_orders.sql"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(
        'TEST (name "orders_from_values");\n\n'
        "WITH __ref__customers AS (\n"
        "    SELECT COLUMN1::VARCHAR AS customer_key, COLUMN2::INTEGER AS order_count\n"
        "    FROM VALUES\n"
        "        ('c1', 1),\n"
        "        ('c2', 2)\n"
        "),\n"
        "__expected__orders AS (SELECT 'c1' AS customer_key, 1 AS order_count)\n"
        "SELECT 1\n",
        encoding="utf-8",
    )
    return project_dir, test_file


def write_snowflake_format_test(*, tmp_path: Path, test_sql: str) -> tuple[Path, Path]:
    """Write a minimal Snowflake-dialect project for real CLI formatting."""

    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "products"\nadapter = "snowflake"\n', encoding="utf-8"
    )
    test_file: Path = tmp_path / "tests" / "unit" / "test_products.sql"
    test_file.parent.mkdir(parents=True)
    test_file.write_text(test_sql, encoding="utf-8")
    return tmp_path, test_file


def prepare_contract_project(tmp_path: Path, *, prod_connection_toml: str = "") -> Path:
    database: Path = tmp_path / "warehouse.duckdb"
    _ = (tmp_path / "sqlbuild_project.toml").write_text(
        (
            'name = "contract_test"\n'
            'adapter = "duckdb"\n'
            'default_target = "dev"\n'
            f'\n[connection]\ndatabase = "{database}"\n'
            '\n[targets.dev]\nschema = "dev"\n'
            '\n[targets.prod]\nschema = "prod"\n'
            f"{prod_connection_toml}"
        ),
        encoding="utf-8",
    )
    models: Path = tmp_path / "models"
    sources: Path = tmp_path / "sources"
    models.mkdir()
    sources.mkdir()
    _ = (models / "orders.sql").write_text(
        """MODEL (
  materialized table
  -- keep model metadata
  columns (
    id ()
  )
);
SELECT CAST(1 AS INTEGER) AS id, CAST('a' AS VARCHAR) AS name
""",
        encoding="utf-8",
    )
    _ = (sources / "raw.yml").write_text(
        """sources:
  - name: raw_orders
    schema: raw
    table: orders
    description: keep source
    columns:
      - name: id
        description: identifier
""",
        encoding="utf-8",
    )
    with duckdb.connect(str(database)) as connection:
        connection.execute("CREATE SCHEMA prod")
        connection.execute("CREATE SCHEMA raw")
        connection.execute("CREATE TABLE prod.orders(id INTEGER, name VARCHAR)")
        connection.execute("CREATE TABLE raw.orders(id BIGINT, status VARCHAR)")
    return database


def add_second_contract_source(*, project_dir: Path, database: Path) -> None:
    """Add another physical source declared in the existing source YAML file."""

    source_path: Path = project_dir / "sources" / "raw.yml"
    _ = source_path.write_text(
        source_path.read_text(encoding="utf-8")
        + """  - name: raw_customers
    schema: raw
    table: customers
    description: keep second source
""",
        encoding="utf-8",
    )
    with duckdb.connect(str(database)) as connection:
        connection.execute("ALTER TABLE raw.orders ADD COLUMN generated_at TIMESTAMP")
        connection.execute("CREATE TABLE raw.customers(customer_id BIGINT, email VARCHAR)")


def compile_finding_keys(*, project_dir: Path, capsys: pytest.CaptureFixture[str]) -> set[str]:
    """Compile through the CLI and return diagnostics as path:code keys."""

    _ = main(["--project-dir", str(project_dir), "compile", "--json"])
    payload: dict[str, object] = json.loads(capsys.readouterr().out)
    diagnostics: list[dict[str, object]] = cast(list[dict[str, object]], payload["diagnostics"])
    return {f"{item['path']}:{item['code']}" for item in diagnostics}
