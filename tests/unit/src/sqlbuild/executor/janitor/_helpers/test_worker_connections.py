"""Worker connection failures surface as the coded warehouse connection error."""

from __future__ import annotations

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.executor.janitor._helpers.workers import open_janitor_worker_connections
from sqlbuild.executor.pipeline.exceptions import WarehouseConnectionError
from tests.unit.src.sqlbuild.executor.janitor._helpers._test_types import (
    JanitorWorkerConnectionFailureTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorWorkerConnectionFailureTestCase(
            description="an unopenable worker connection raises the coded connection error",
            connection_count=2,
            expected_code="C115",
            expected_message="could not connect to the duckdb warehouse",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unreachable_warehouse_when_opening_worker_connections_then_error_is_coded(
    test_case: JanitorWorkerConnectionFailureTestCase,
) -> None:
    with pytest.raises(WarehouseConnectionError) as raised:
        _ = open_janitor_worker_connections(
            adapter=DuckDbAdapter(),
            connection_config={"database": "/nonexistent-directory/orders/janitor.duckdb"},
            count=test_case.connection_count,
            progress=None,
        )

    assert raised.value.code == test_case.expected_code
    assert test_case.expected_message in raised.value.message
