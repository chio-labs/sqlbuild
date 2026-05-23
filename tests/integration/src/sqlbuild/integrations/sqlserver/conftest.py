from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.integrations.sqlserver.client import SqlServerAdapter
from tests.integration.src.sqlbuild.integrations.sqlserver.helpers import build_unique_schema_name


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    test_dir: Path = Path(__file__).resolve().parent
    for item in items:
        if not Path(str(item.path)).resolve().is_relative_to(test_dir):
            continue
        item.add_marker(pytest.mark.real_warehouse)
        item.add_marker(pytest.mark.sqlserver)


@pytest.fixture(scope="session")
def sqlserver_container_config() -> dict[str, object]:
    return {
        "host": os.environ.get("SQLBUILD_SQLSERVER_HOST", "localhost"),
        "port": int(os.environ.get("SQLBUILD_SQLSERVER_PORT", "1433")),
        "database": os.environ.get("SQLBUILD_SQLSERVER_DATABASE", "tempdb"),
        "user": os.environ.get("SQLBUILD_SQLSERVER_USER", "sa"),
        "password": os.environ.get("SQLBUILD_SQLSERVER_PASSWORD", "Sqlbuild!2026"),
    }


@pytest.fixture
def adapter() -> SqlServerAdapter:
    return SqlServerAdapter()


@pytest.fixture
def sqlserver_schema() -> str:
    return build_unique_schema_name(prefix="sqb_integration")


@pytest.fixture
def connection(
    adapter: SqlServerAdapter,
    sqlserver_container_config: dict[str, object],
    sqlserver_schema: str,
) -> Iterator[Any]:
    conn: Any = adapter.connect(sqlserver_container_config)
    adapter.execute(conn, f"CREATE SCHEMA {adapter.render_identifier(sqlserver_schema)}")
    try:
        yield conn
    finally:
        adapter.execute(
            conn,
            "DECLARE @sql NVARCHAR(MAX) = N''; "
            "SELECT @sql += N'DROP TABLE ' + QUOTENAME(s.name) + N'.' + QUOTENAME(t.name) + N';' "
            "FROM sys.tables t JOIN sys.schemas s ON t.schema_id = s.schema_id "
            f"WHERE s.name = '{sqlserver_schema}'; "
            "EXEC sp_executesql @sql;",
        )
        adapter.execute(conn, f"DROP SCHEMA {adapter.render_identifier(sqlserver_schema)}")
        adapter.close(conn)
