from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[Any]:
    from testcontainers.postgres import PostgresContainer

    try:
        with PostgresContainer("postgres:17") as container:
            yield container
    except Exception as exc:
        pytest.skip(f"Docker not available for Postgres testcontainer: {exc}")


@pytest.fixture(scope="session")
def postgres_config(postgres_container: Any) -> dict[str, object]:
    return {
        "host": postgres_container.get_container_host_ip(),
        "port": int(postgres_container.get_exposed_port(5432)),
        "dbname": postgres_container.dbname,
        "user": postgres_container.username,
        "password": postgres_container.password,
    }
