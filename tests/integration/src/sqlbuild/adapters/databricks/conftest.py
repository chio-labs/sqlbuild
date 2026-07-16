from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from tests.integration.src.sqlbuild.adapters.databricks.helpers import (
    build_databricks_connection_config,
    build_unique_schema_name,
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    test_dir: Path = Path(__file__).resolve().parent
    for item in items:
        if not Path(str(item.path)).resolve().is_relative_to(test_dir):
            continue
        item.add_marker(pytest.mark.real_warehouse)
        item.add_marker(pytest.mark.databricks)


@pytest.fixture
def adapter() -> DatabricksAdapter:
    return DatabricksAdapter()


@pytest.fixture
def databricks_catalog() -> str:
    return str(build_databricks_connection_config()["catalog"])


@pytest.fixture
def databricks_schema() -> str:
    return build_unique_schema_name(prefix="sqlbuild_integration")


@pytest.fixture
def connection(
    adapter: DatabricksAdapter,
    databricks_catalog: str,
    databricks_schema: str,
) -> Iterator[Any]:
    config: dict[str, object] = build_databricks_connection_config(schema=databricks_schema)
    schema_target: str = f"{databricks_catalog}.{databricks_schema}"
    conn: Any = adapter.connect(config)
    adapter.execute(connection=conn, sql=f"CREATE SCHEMA IF NOT EXISTS {schema_target}")
    try:
        yield conn
    finally:
        adapter.execute(connection=conn, sql=f"DROP SCHEMA IF EXISTS {schema_target} CASCADE")
        adapter.close(conn)
