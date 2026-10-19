from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.clickhouse.helpers import CLICKHOUSE_IMAGE


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
        with ClickHouseContainer(CLICKHOUSE_IMAGE) as container:
            yield {
                "host": container.get_container_host_ip(),
                "port": int(container.get_exposed_port(8123)),
                "user": container.username,
                "password": container.password,
            }
    except Exception as exc:
        pytest.skip(f"Docker not available for ClickHouse testcontainer: {exc}")
