from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.integrations.postgres.client import PostgresAdapter
from tests.integration.src.sqlbuild.integrations.postgres.helpers import (
    build_postgres_connection_config,
    build_unique_schema_name,
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    test_dir: Path = Path(__file__).resolve().parent
    for item in items:
        if not Path(str(item.path)).resolve().is_relative_to(test_dir):
            continue
        item.add_marker(pytest.mark.real_warehouse)
        item.add_marker(pytest.mark.postgres)


@pytest.fixture
def adapter() -> PostgresAdapter:
    return PostgresAdapter()


@pytest.fixture
def postgres_schema() -> str:
    return build_unique_schema_name(prefix="sqb_integration")


@pytest.fixture
def connection(
    adapter: PostgresAdapter,
    postgres_schema: str,
) -> Iterator[Any]:
    config: dict[str, object] = build_postgres_connection_config()
    conn: Any = adapter.connect(config)
    adapter.execute(conn, f"CREATE SCHEMA IF NOT EXISTS {postgres_schema}")
    try:
        yield conn
    finally:
        adapter.execute(conn, f"DROP SCHEMA IF EXISTS {postgres_schema} CASCADE")
        adapter.close(conn)
