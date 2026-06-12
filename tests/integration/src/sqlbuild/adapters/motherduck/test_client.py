from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.adapter.shared.models import QueryResult, StatementRecorder
from sqlbuild.adapters.motherduck.client import MotherDuckAdapter
from tests.integration.src.sqlbuild.adapters.motherduck._test_types import (
    MotherDuckBuildFlowTestCase,
    MotherDuckQueryTestCase,
)
from tests.integration.src.sqlbuild.adapters.motherduck.helpers import (
    fetch_rows,
    qualified_name,
)


@pytest.mark.parametrize(
    "test_case",
    [
        MotherDuckQueryTestCase(
            description="returns inline query result with column names and rows",
            sql="SELECT 1 AS id, 'hello' AS name",
            expected_result=QueryResult(columns=("id", "name"), rows=((1, "hello"),)),
        )
    ],
    ids=["returns inline query result with column names and rows"],
)
def test_given_sql_when_querying_then_motherduck_returns_named_rows(
    test_case: MotherDuckQueryTestCase,
    adapter: MotherDuckAdapter,
    connection: Any,
) -> None:
    result: QueryResult = adapter.query(connection, test_case.sql, limit=None)

    assert result == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    [
        MotherDuckBuildFlowTestCase(
            description="creates table from query using DuckDB materialization semantics",
            table_name="fact_orders",
            source_sql="SELECT 1 AS id UNION ALL SELECT 2 AS id",
            expected_row_count=2,
        )
    ],
    ids=["creates table from query using DuckDB materialization semantics"],
)
def test_given_model_sql_when_building_then_motherduck_creates_table(
    test_case: MotherDuckBuildFlowTestCase,
    adapter: MotherDuckAdapter,
    connection: Any,
    motherduck_schema: str,
) -> None:
    target: str = qualified_name(schema=motherduck_schema, name=test_case.table_name)

    adapter.create_table_as(
        connection,
        destination=target,
        sql=test_case.source_sql,
        statement_recorder=StatementRecorder(),
    )

    rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter,
        connection=connection,
        sql=f"SELECT COUNT(*) FROM {target}",
    )
    assert rows[0][0] == test_case.expected_row_count
