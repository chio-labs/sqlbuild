from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.clickhouse.helpers import (
    CLICKHOUSE_IMAGE,
    build_unique_schema_name,
    cleanup_clickhouse_schema,
    execute_clickhouse_sql,
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    test_dir: Path = Path(__file__).resolve().parent
    for item in items:
        if not Path(str(item.path)).resolve().is_relative_to(test_dir):
            continue
        item.add_marker(pytest.mark.real_warehouse)
        item.add_marker(pytest.mark.clickhouse)


@pytest.fixture(scope="session")
def clickhouse_e2e_config() -> Iterator[dict[str, object]]:
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
        with ClickHouseContainer(CLICKHOUSE_IMAGE).with_env(
            "CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT", "1"
        ) as container:
            yield {
                "host": container.get_container_host_ip(),
                "port": int(container.get_exposed_port(8123)),
                "user": container.username,
                "password": container.password,
            }
    except Exception as exc:
        pytest.skip(f"Docker not available for ClickHouse testcontainer: {exc}")


@pytest.fixture
def recall_database(clickhouse_e2e_config: dict[str, object]) -> Iterator[str]:
    database: str = build_unique_schema_name(prefix="recall")
    execute_clickhouse_sql(
        config=clickhouse_e2e_config, statements=(f"CREATE DATABASE {database}",)
    )
    yield database
    execute_clickhouse_sql(
        config=clickhouse_e2e_config, statements=(f"DROP DATABASE IF EXISTS {database} SYNC",)
    )


@pytest.fixture
def janitor_schema(clickhouse_e2e_config: dict[str, object]) -> Iterator[str]:
    schema: str = build_unique_schema_name(prefix="janitor_usage")
    yield schema
    cleanup_clickhouse_schema(config=clickhouse_e2e_config, schema_name=schema)
