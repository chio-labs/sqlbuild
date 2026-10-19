from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from tests.integration.src.sqlbuild.adapters.clickhouse.helpers import (
    CLICKHOUSE_IMAGE,
    build_unique_schema_name,
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    test_dir: Path = Path(__file__).resolve().parent
    for item in items:
        if not Path(str(item.path)).resolve().is_relative_to(test_dir):
            continue
        item.add_marker(pytest.mark.real_warehouse)
        item.add_marker(pytest.mark.clickhouse)


@pytest.fixture(scope="session")
def clickhouse_config() -> Iterator[dict[str, object]]:
    port: str | None = os.environ.get("SQLBUILD_TEST_CLICKHOUSE_PORT")
    if port is not None:
        yield {
            "host": os.environ.get("SQLBUILD_TEST_CLICKHOUSE_HOST", "localhost"),
            "port": int(port),
            "user": os.environ.get("SQLBUILD_TEST_CLICKHOUSE_USER", "default"),
            "password": os.environ.get("SQLBUILD_TEST_CLICKHOUSE_PASSWORD", ""),
        }
        return
    from testcontainers.clickhouse import ClickHouseContainer

    try:
        with ClickHouseContainer(CLICKHOUSE_IMAGE) as container:
            yield {
                "host": container.get_container_host_ip(),
                "port": int(container.get_exposed_port(8123)),
                "user": container.username,
                "password": container.password,
            }
    except Exception as exc:
        pytest.skip(f"Docker not available for ClickHouse testcontainer: {exc}")


@pytest.fixture
def adapter() -> ClickHouseAdapter:
    return ClickHouseAdapter()


@pytest.fixture
def clickhouse_schema() -> str:
    return build_unique_schema_name(prefix="sqb_integration")


@pytest.fixture
def connection(
    adapter: ClickHouseAdapter, clickhouse_config: dict[str, object], clickhouse_schema: str
) -> Iterator[Any]:
    conn: Any = adapter.connect(dict(clickhouse_config))
    adapter.execute(connection=conn, sql=f"CREATE DATABASE IF NOT EXISTS {clickhouse_schema}")
    try:
        yield conn
    finally:
        adapter.execute(connection=conn, sql=f"DROP DATABASE IF EXISTS {clickhouse_schema} SYNC")
        adapter.close(conn)
