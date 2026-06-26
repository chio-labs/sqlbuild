from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.integrations.dbt.helpers.planning.concurrent_reads import (
    run_state_reads_in_parallel,
)
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    ConcurrentStateReadsErrorTestCase,
    ConcurrentStateReadsTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import ConnectionTrackingAdapter


@pytest.mark.parametrize(
    "test_case",
    [
        ConcurrentStateReadsTestCase(
            description="returns each read result keyed by name on its own connection",
            read_names=("fingerprints", "source_freshness", "existing_relation_keys"),
            expected_results={
                "fingerprints": "result_fingerprints",
                "source_freshness": "result_source_freshness",
                "existing_relation_keys": "result_existing_relation_keys",
            },
            expected_open_connection_count=3,
        )
    ],
    ids=["returns each read result keyed by name on its own connection"],
)
def test_given_independent_reads_when_running_in_parallel_then_returns_results_per_connection(
    test_case: ConcurrentStateReadsTestCase,
) -> None:
    adapter: ConnectionTrackingAdapter = ConnectionTrackingAdapter()
    seen_connections: list[object] = []

    def make_read(name: str) -> Any:
        def read(connection: Any) -> str:
            seen_connections.append(connection)
            return f"result_{name}"

        return read

    results: dict[str, str] = run_state_reads_in_parallel(
        adapter=adapter,
        connection_config={},
        reads={name: make_read(name) for name in test_case.read_names},
    )

    assert results == test_case.expected_results
    assert len(adapter.opened_connections) == test_case.expected_open_connection_count
    assert len(adapter.closed_connections) == test_case.expected_open_connection_count
    assert set(adapter.opened_connections) == set(adapter.closed_connections)
    assert len(set(seen_connections)) == len(test_case.read_names)


@pytest.mark.parametrize(
    "test_case",
    [
        ConcurrentStateReadsErrorTestCase(
            description="propagates the failing read error and still closes every connection",
            failing_read_name="boom",
            expected_error_message="read boom",
            expected_open_connection_count=2,
        )
    ],
    ids=["propagates the failing read error and still closes every connection"],
)
def test_given_a_failing_read_when_running_in_parallel_then_propagates_and_closes_connections(
    test_case: ConcurrentStateReadsErrorTestCase,
) -> None:
    adapter: ConnectionTrackingAdapter = ConnectionTrackingAdapter()

    def ok_read(connection: Any) -> str:
        del connection
        return "ok"

    def failing_read(connection: Any) -> str:
        del connection
        raise ValueError(test_case.expected_error_message)

    with pytest.raises(ValueError, match=test_case.expected_error_message):
        run_state_reads_in_parallel(
            adapter=adapter,
            connection_config={},
            reads={"ok": ok_read, test_case.failing_read_name: failing_read},
        )

    assert len(adapter.opened_connections) == test_case.expected_open_connection_count
    assert set(adapter.opened_connections) == set(adapter.closed_connections)
