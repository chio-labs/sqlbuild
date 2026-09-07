from __future__ import annotations

from pathlib import Path

import duckdb


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
