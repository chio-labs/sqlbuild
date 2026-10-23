"""Warehouse server fixtures shared by the per-warehouse and cross-warehouse E2E suites."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.clickhouse.helpers import CLICKHOUSE_IMAGE


@pytest.fixture(scope="session")
def postgres_e2e_container() -> Any:
    from testcontainers.postgres import PostgresContainer

    try:
        with PostgresContainer("postgres:17") as container:
            yield container
    except Exception as exc:
        pytest.skip(f"Docker not available for Postgres testcontainer: {exc}")


@pytest.fixture(scope="session")
def postgres_e2e_config(postgres_e2e_container: Any) -> dict[str, object]:
    return {
        "host": postgres_e2e_container.get_container_host_ip(),
        "port": int(postgres_e2e_container.get_exposed_port(5432)),
        "dbname": postgres_e2e_container.dbname,
        "user": postgres_e2e_container.username,
        "password": postgres_e2e_container.password,
    }


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
