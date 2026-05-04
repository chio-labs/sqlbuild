from __future__ import annotations

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        item.add_marker(pytest.mark.real_warehouse)
        item.add_marker(pytest.mark.snowflake)
