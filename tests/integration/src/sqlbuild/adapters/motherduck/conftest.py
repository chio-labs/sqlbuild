from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.motherduck.classes.motherduck_adapter import MotherDuckAdapter
from tests.integration.src.sqlbuild.adapters.motherduck.helpers import (
    build_motherduck_connection_config,
    build_unique_schema_name,
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    test_dir: Path = Path(__file__).resolve().parent
    for item in items:
        if not Path(str(item.path)).resolve().is_relative_to(test_dir):
            continue
        item.add_marker(pytest.mark.real_warehouse)
        item.add_marker(pytest.mark.motherduck)


@pytest.fixture
def adapter() -> MotherDuckAdapter:
    return MotherDuckAdapter()


@pytest.fixture
def motherduck_schema() -> str:
    return build_unique_schema_name(prefix="sqlbuild_motherduck")


@pytest.fixture
def connection(
    adapter: MotherDuckAdapter,
    motherduck_schema: str,
) -> Iterator[Any]:
    config: dict[str, object] = build_motherduck_connection_config()
    conn: Any = adapter.connect(config)
    adapter.execute(connection=conn, sql=f"CREATE SCHEMA IF NOT EXISTS {motherduck_schema}")
    try:
        yield conn
    finally:
        adapter.execute(connection=conn, sql=f"DROP SCHEMA IF EXISTS {motherduck_schema} CASCADE")
        adapter.close(conn)
