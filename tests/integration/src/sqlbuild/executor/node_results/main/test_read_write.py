"""Integration tests for node result read/write operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.executor.node_results.main.read import read_node_results
from sqlbuild.executor.node_results.main.write import write_node_result_record
from sqlbuild.executor.node_results.models import (
    NodeResultEnvelope,
    NodeResultQuery,
    NodeResultRecord,
)
from tests.integration.src.sqlbuild.executor.node_results.main._test_types import (
    NodeResultReadWriteIntegrationTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        NodeResultReadWriteIntegrationTestCase(
            description="writes and reads node result through DuckDB",
            expected_payload={"value": 42},
            expected_metadata={"source": "integration"},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_node_result_record_when_writing_and_reading_then_round_trips_envelope(
    test_case: NodeResultReadWriteIntegrationTestCase,
    tmp_path: Path,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "node_results.duckdb")})
    try:
        write_node_result_record(
            connection=connection,
            execute=adapter.execute,
            database=None,
            schema="main",
            record=NodeResultRecord(
                node_type="task",
                node_name="produce_result",
                target_database=None,
                target_schema="main",
                target_name=None,
                run_id="run_1",
                status="success",
                payload=test_case.expected_payload,
                metadata=test_case.expected_metadata,
            ),
            render_qualified_name=adapter.render_qualified_name,
            render_framework_type=adapter.render_framework_type,
            render_create_index_sqls=adapter.render_create_node_result_index_sqls,
        )

        results: tuple[NodeResultEnvelope, ...] = read_node_results(
            connection=connection,
            execute=adapter.execute,
            relation_exists=adapter.relation_exists,
            database=None,
            schema="main",
            query=NodeResultQuery(
                node_type="task",
                node_name="produce_result",
                target_database=None,
                target_schema="main",
                target_name=None,
                statuses=("success",),
                run_id=None,
                limit=1,
            ),
            render_qualified_name=adapter.render_qualified_name,
        )
    finally:
        adapter.close(connection)

    assert len(results) == 1
    assert results[0].payload == test_case.expected_payload
    assert results[0].metadata == test_case.expected_metadata
