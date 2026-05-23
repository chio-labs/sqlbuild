from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    test_dir: Path = Path(__file__).resolve().parent
    for item in items:
        if not Path(str(item.path)).resolve().is_relative_to(test_dir):
            continue
        item.add_marker(pytest.mark.real_warehouse)
        item.add_marker(pytest.mark.postgres)


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
