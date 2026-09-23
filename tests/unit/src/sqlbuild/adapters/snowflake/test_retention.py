from typing import Any, cast

import pytest

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapter.contract.models import (
    RenderedRetentionChange,
    RetentionRequest,
    RetentionState,
)
from sqlbuild.adapter.contract.types import RetentionChangePhase, RetentionScope
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from tests.unit.src.sqlbuild.adapters.snowflake._test_types import (
    SnowflakeBatchedRetentionErrorTestCase,
    SnowflakeBatchedRetentionTestCase,
    SnowflakeRetentionTestCase,
)
from tests.unit.src.sqlbuild.adapters.snowflake.helpers import (
    FakeSnowflakeMetadataConnection,
    FakeSnowflakeMetadataCursor,
    FakeSnowflakeMetadataSequenceConnection,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeRetentionTestCase(
            description="transient table retention is inspected and altered without conversion",
            desired_days=7,
            observed_row=(3, "YES"),
            expected_days=3,
            expected_kind="TRANSIENT",
            expected_sql=("ALTER TABLE analytics.mart.results SET DATA_RETENTION_TIME_IN_DAYS = 7"),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_snowflake_relation_when_managing_retention_then_observes_and_renders_alter(
    test_case: SnowflakeRetentionTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()
    cursor: FakeSnowflakeMetadataCursor = FakeSnowflakeMetadataCursor(row=test_case.observed_row)
    connection: FakeSnowflakeMetadataConnection = FakeSnowflakeMetadataConnection(cursor)
    request: RetentionRequest = RetentionRequest(
        request_id="model.results",
        scope=RetentionScope.RELATION,
        database="analytics",
        schema="mart",
        name="results",
        desired_days=test_case.desired_days,
    )

    state: RetentionState = adapter.inspect_retention(
        connection=cast(Any, connection), request=request
    )
    changes: tuple[RenderedRetentionChange, ...] = adapter.render_retention_changes(request=request)

    assert state.effective_days == test_case.expected_days
    assert state.relation_kind == test_case.expected_kind
    assert state.is_transient is True
    assert changes[0].phase == RetentionChangePhase.ALTER
    assert changes[0].statements == (test_case.expected_sql,)
    assert cursor.executed_sql is not None
    assert "retention_time, is_transient" in cursor.executed_sql


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeBatchedRetentionTestCase(
            description="three tables in two schemas take one metadata query per schema",
            requests=(("mart", "orders"), ("mart", "customers"), ("staging", "stg_orders")),
            schema_rows=(
                [("ORDERS", 7, "NO"), ("CUSTOMERS", 1, "NO")],
                [("STG_ORDERS", 0, "YES")],
            ),
            expected_query_schemas=("MART", "STAGING"),
            expected_days={"orders": 7, "customers": 1, "stg_orders": 0},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_many_relations_when_inspecting_retention_then_queries_once_per_schema(
    test_case: SnowflakeBatchedRetentionTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()
    cursors: tuple[FakeSnowflakeMetadataCursor, ...] = tuple(
        FakeSnowflakeMetadataCursor(rows=rows) for rows in test_case.schema_rows
    )
    connection: FakeSnowflakeMetadataSequenceConnection = FakeSnowflakeMetadataSequenceConnection(
        cursors
    )
    requests: tuple[RetentionRequest, ...] = tuple(
        RetentionRequest(
            request_id=name,
            scope=RetentionScope.RELATION,
            database="analytics",
            schema=schema,
            name=name,
            desired_days=7,
        )
        for schema, name in test_case.requests
    )

    states: dict[str, RetentionState] = adapter.inspect_retentions(
        connection=cast(Any, connection), requests=requests
    )

    assert (
        tuple(
            cast(tuple[object, ...], cursor.executed_params)[-2]
            for cursor in connection.returned_cursors
        )
        == test_case.expected_query_schemas
    )
    assert {request_id: state.effective_days for request_id, state in states.items()} == (
        test_case.expected_days
    )


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeBatchedRetentionErrorTestCase(
            description="a table missing from metadata fails like single inspection",
            requests=(("mart", "orders"), ("mart", "customers")),
            rows=[("ORDERS", 7, "NO")],
            expected_error="Snowflake retention metadata not found for customers",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_missing_relation_when_batch_inspecting_retention_then_raises(
    test_case: SnowflakeBatchedRetentionErrorTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()
    connection: FakeSnowflakeMetadataConnection = FakeSnowflakeMetadataConnection(
        FakeSnowflakeMetadataCursor(rows=test_case.rows)
    )
    requests: tuple[RetentionRequest, ...] = tuple(
        RetentionRequest(
            request_id=name,
            scope=RetentionScope.RELATION,
            database="analytics",
            schema=schema,
            name=name,
            desired_days=7,
        )
        for schema, name in test_case.requests
    )

    with pytest.raises(AdapterUserError, match=test_case.expected_error):
        adapter.inspect_retentions(connection=cast(Any, connection), requests=requests)
