from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.clickhouse.helpers import (
    build_unique_schema_name,
    execute_clickhouse_sql,
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    test_dir: Path = Path(__file__).resolve().parent
    for item in items:
        if not Path(str(item.path)).resolve().is_relative_to(test_dir):
            continue
        item.add_marker(pytest.mark.real_warehouse)
        item.add_marker(pytest.mark.clickhouse)


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
