from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.bigquery.client import BigQueryAdapter
from tests.integration.src.sqlbuild.adapters.bigquery.helpers import (
    build_bigquery_connection_config,
    build_unique_dataset_name,
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    test_dir: Path = Path(__file__).resolve().parent
    for item in items:
        if not Path(str(item.path)).resolve().is_relative_to(test_dir):
            continue
        item.add_marker(pytest.mark.real_warehouse)
        item.add_marker(pytest.mark.bigquery)


@pytest.fixture
def adapter() -> BigQueryAdapter:
    return BigQueryAdapter()


@pytest.fixture
def bigquery_project() -> str:
    return str(build_bigquery_connection_config()["project"])


@pytest.fixture
def bigquery_dataset() -> str:
    return build_unique_dataset_name(prefix="sqlbuild_integration")


@pytest.fixture
def connection(
    adapter: BigQueryAdapter,
    bigquery_project: str,
    bigquery_dataset: str,
) -> Iterator[Any]:
    config: dict[str, object] = build_bigquery_connection_config(schema=bigquery_dataset)
    conn: Any = adapter.connect(config)
    dataset_id: str = f"{bigquery_project}.{bigquery_dataset}"
    try:
        from google.cloud import bigquery

        dataset: Any = bigquery.Dataset(dataset_id)
        dataset.location = conn.location
        conn.client.create_dataset(dataset, exists_ok=True)
        yield conn
    finally:
        conn.client.delete_dataset(dataset_id, delete_contents=True, not_found_ok=True)
        adapter.close(conn)
