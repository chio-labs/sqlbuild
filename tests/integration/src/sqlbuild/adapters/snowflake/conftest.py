from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.snowflake.client import SnowflakeAdapter
from tests.integration.src.sqlbuild.adapters.snowflake.helpers import (
    build_snowflake_connection_config,
    build_unique_schema_name,
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    test_dir: Path = Path(__file__).resolve().parent
    for item in items:
        if not Path(str(item.path)).resolve().is_relative_to(test_dir):
            continue
        item.add_marker(pytest.mark.real_warehouse)
        item.add_marker(pytest.mark.snowflake)


@pytest.fixture
def adapter() -> SnowflakeAdapter:
    return SnowflakeAdapter()


@pytest.fixture
def snowflake_database() -> str:
    return str(build_snowflake_connection_config()["database"])


@pytest.fixture
def snowflake_schema() -> str:
    return build_unique_schema_name(prefix="sqlbuild_integration")


@pytest.fixture
def connection(
    adapter: SnowflakeAdapter,
    snowflake_database: str,
    snowflake_schema: str,
) -> Iterator[Any]:
    config: dict[str, object] = build_snowflake_connection_config(schema=snowflake_schema)
    schema_target: str = f"{snowflake_database}.{snowflake_schema}"
    conn: Any = adapter.connect(config)
    adapter.execute(conn, f"CREATE SCHEMA IF NOT EXISTS {schema_target}")
    try:
        yield conn
    finally:
        adapter.execute(conn, f"DROP SCHEMA IF EXISTS {schema_target} CASCADE")
        adapter.close(conn)
