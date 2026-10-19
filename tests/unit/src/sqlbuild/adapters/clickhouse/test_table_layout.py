from __future__ import annotations

import pytest

from sqlbuild.adapters.clickhouse._helpers.table_layout import render_table_layout
from tests.unit.src.sqlbuild.adapters.clickhouse._test_types import TableLayoutTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        TableLayoutTestCase(
            description="no layout keeps an unsorted MergeTree",
            layout={},
            expected_clauses="ENGINE = MergeTree ORDER BY tuple()",
        ),
        TableLayoutTestCase(
            description="every clause",
            layout={
                "engine": "ReplacingMergeTree(version)",
                "order_by": ["customer_id", "toDate(ordered_at)"],
                "partition_by": "toYYYYMM(ordered_at)",
                "primary_key": ["customer_id"],
                "table_settings": {
                    "index_granularity": 4096,
                    "allow_nullable_key": True,
                    "storage_policy": "default",
                },
            },
            expected_clauses=(
                "ENGINE = ReplacingMergeTree(version) ORDER BY (customer_id, toDate(ordered_at)) "
                "PARTITION BY toYYYYMM(ordered_at) PRIMARY KEY (customer_id) "
                "SETTINGS index_granularity = 4096, allow_nullable_key = 1, "
                "storage_policy = 'default'"
            ),
        ),
        TableLayoutTestCase(
            description="a single sorting expression",
            layout={"order_by": "order_id"},
            expected_clauses="ENGINE = MergeTree ORDER BY (order_id)",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_model_layout_when_rendering_then_clickhouse_table_clauses_result(
    test_case: TableLayoutTestCase,
) -> None:
    assert render_table_layout(test_case.layout) == test_case.expected_clauses
