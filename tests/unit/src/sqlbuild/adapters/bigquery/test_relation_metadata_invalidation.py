"""BigQuery copy and load jobs change relations without SQL, so they evict cached metadata."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.adapter.relations.main.cached_relation_columns import cached_relation_columns
from sqlbuild.adapter.relations.main.relation_metadata_cache_scope import (
    relation_metadata_cache_scope,
)
from sqlbuild.adapters.bigquery.classes.bigquery_connection import _BigQueryConnection
from tests.unit.src.sqlbuild.adapters.bigquery._test_types import BigQueryJobInvalidationTestCase
from tests.unit.src.sqlbuild.adapters.bigquery.helpers import (
    CountingColumnsBigQueryAdapter,
    FakeBigQueryJobClient,
    run_bigquery_job,
)

_RELATIONS: tuple[str, ...] = ("orders", "orders__stage", "customers")


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryJobInvalidationTestCase(
            description="copy job evicts destination and origin",
            operation="copy",
            expected_reads={"orders": 2, "orders__stage": 2, "customers": 1},
        ),
        BigQueryJobInvalidationTestCase(
            description="seed load job evicts its destination",
            operation="load",
            expected_reads={"orders": 2, "orders__stage": 1, "customers": 1},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_bigquery_job_when_looking_up_again_then_changed_relations_are_reread(
    test_case: BigQueryJobInvalidationTestCase, tmp_path: Path
) -> None:
    adapter: CountingColumnsBigQueryAdapter = CountingColumnsBigQueryAdapter()
    connection: _BigQueryConnection = _BigQueryConnection(
        client=FakeBigQueryJobClient(), location=None
    )
    seed_path: Path = tmp_path / "orders.csv"
    _ = seed_path.write_text("order_id\n1\n", encoding="utf-8")

    with relation_metadata_cache_scope(adapter=adapter):
        name: str
        for name in _RELATIONS:
            _ = cached_relation_columns(
                adapter=adapter, connection=connection, database=None, schema="marts", name=name
            )
        run_bigquery_job(
            operation=test_case.operation,
            adapter=adapter,
            connection=connection,
            seed_path=seed_path,
        )
        for name in _RELATIONS:
            _ = cached_relation_columns(
                adapter=adapter, connection=connection, database=None, schema="marts", name=name
            )

    assert adapter.column_reads == test_case.expected_reads


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
