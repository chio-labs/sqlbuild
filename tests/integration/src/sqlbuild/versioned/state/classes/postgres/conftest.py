from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.versioned.state.classes.postgres import PostgresStateBackend
from tests.integration.src.sqlbuild.versioned.state.classes.postgres.helpers import (
    build_unique_schema_name,
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    test_dir: Path = Path(__file__).resolve().parent
    for item in items:
        if not Path(str(item.path)).resolve().is_relative_to(test_dir):
            continue
        item.add_marker(pytest.mark.real_warehouse)
        item.add_marker(pytest.mark.postgres)


@pytest.fixture(scope="session")
def postgres_state_container() -> Iterator[Any]:
    from testcontainers.postgres import PostgresContainer

    try:
        with PostgresContainer("postgres:17") as container:
            yield container
    except Exception as exc:
        pytest.skip(f"Docker not available for Postgres testcontainer: {exc}")


@pytest.fixture(scope="session")
def postgres_state_config(postgres_state_container: Any) -> dict[str, object]:
    return {
        "host": postgres_state_container.get_container_host_ip(),
        "port": int(postgres_state_container.get_exposed_port(5432)),
        "dbname": postgres_state_container.dbname,
        "user": postgres_state_container.username,
        "password": postgres_state_container.password,
    }


@pytest.fixture
def postgres_state_schema() -> str:
    return build_unique_schema_name(prefix="sqb_state")


@pytest.fixture
def postgres_state_backend() -> PostgresStateBackend:
    return PostgresStateBackend()


@pytest.fixture
def postgres_state_connection(
    postgres_state_backend: PostgresStateBackend,
    postgres_state_config: dict[str, object],
    postgres_state_schema: str,
) -> Iterator[Any]:
    connection: Any = postgres_state_backend.connect(postgres_state_config)
    try:
        yield connection
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f'DROP SCHEMA IF EXISTS "{postgres_state_schema}" CASCADE')
            cursor.execute(
                "SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE %s",
                [f"{postgres_state_schema}__backup_%"],
            )
            backup_schemas: list[str] = [row[0] for row in cursor.fetchall()]
            backup_schema: str
            for backup_schema in backup_schemas:
                cursor.execute(f'DROP SCHEMA IF EXISTS "{backup_schema}" CASCADE')
        postgres_state_backend.close(connection)
