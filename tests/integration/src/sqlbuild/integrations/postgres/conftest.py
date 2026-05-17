from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from sqlbuild.integrations.postgres.client import PostgresAdapter
from tests.integration.src.sqlbuild.integrations.postgres.helpers import build_unique_schema_name


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[Any]:
    from testcontainers.postgres import PostgresContainer

    try:
        with PostgresContainer("postgres:17") as container:
            yield container
    except Exception as exc:
        pytest.skip(f"Docker not available for Postgres testcontainer: {exc}")


@pytest.fixture(scope="session")
def postgres_container_config(postgres_container: Any) -> dict[str, object]:
    return {
        "host": postgres_container.get_container_host_ip(),
        "port": int(postgres_container.get_exposed_port(5432)),
        "dbname": postgres_container.dbname,
        "user": postgres_container.username,
        "password": postgres_container.password,
    }


@pytest.fixture
def adapter() -> PostgresAdapter:
    return PostgresAdapter()


@pytest.fixture
def postgres_schema() -> str:
    return build_unique_schema_name(prefix="sqb_integration")


@pytest.fixture
def connection(
    adapter: PostgresAdapter,
    postgres_container_config: dict[str, object],
    postgres_schema: str,
) -> Iterator[Any]:
    conn: Any = adapter.connect(postgres_container_config)
    adapter.execute(conn, f"CREATE SCHEMA IF NOT EXISTS {postgres_schema}")
    try:
        yield conn
    finally:
        adapter.execute(conn, f"DROP SCHEMA IF EXISTS {postgres_schema} CASCADE")
        adapter.close(conn)
