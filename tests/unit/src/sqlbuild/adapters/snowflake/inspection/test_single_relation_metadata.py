"""Build-path single-relation existence and column reads use SHOW, never INFORMATION_SCHEMA."""

from __future__ import annotations

import pytest

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.adapters.snowflake.classes.snowflake_connection import _SnowflakeConnection
from tests.unit.src.sqlbuild.adapters.snowflake.inspection._test_types import (
    ShowColumnsEquivalenceTestCase,
    SingleRelationErrorTestCase,
    SingleRelationLookupTestCase,
)
from tests.unit.src.sqlbuild.adapters.snowflake.inspection.helpers import (
    FakeColumn,
    FakeRelation,
    OfflineSnowflakeAdapter,
    RecordingSnowflakeWarehouse,
    attempted_query_kinds,
    build_offline_snowflake,
)

_TYPED_COLUMNS: tuple[FakeColumn, ...] = (
    FakeColumn(name="ORDER_ID", data_type="NUMBER", numeric_precision=38, numeric_scale=0),
    FakeColumn(name="AMOUNT", data_type="NUMBER", numeric_precision=10, numeric_scale=2),
    FakeColumn(name="STATUS", data_type="TEXT", character_maximum_length=40),
    FakeColumn(name="RATE", data_type="FLOAT", character_maximum_length=None),
    FakeColumn(name="ORDERED_AT", data_type="TIMESTAMP_NTZ", character_maximum_length=None),
    FakeColumn(name="PAYLOAD", data_type="VARIANT", character_maximum_length=None),
)
_RELATIONS: tuple[FakeRelation, ...] = (
    FakeRelation(database="ANALYTICS", schema="STAGING", name="ORDERS", columns=_TYPED_COLUMNS),
    FakeRelation(
        database="ANALYTICS",
        schema="STAGING",
        name="ORDERS_V",
        table_type="VIEW",
        columns=_TYPED_COLUMNS[:2],
    ),
    FakeRelation(database="ANALYTICS", schema="STAGING", name="ORDERSXDELTA"),
)


@pytest.mark.parametrize(
    "test_case",
    [
        SingleRelationLookupTestCase(
            description="table answered by SHOW TABLES and SHOW COLUMNS IN TABLE",
            database="analytics",
            schema="staging",
            name="orders",
            expected_exists=True,
            expected_column_names=("order_id", "amount", "status", "rate", "ordered_at", "payload"),
            expected_query_kinds=("show_relation_lookup", "show_columns"),
        ),
        SingleRelationLookupTestCase(
            description="view falls through to SHOW VIEWS",
            database="analytics",
            schema="staging",
            name="orders_v",
            expected_exists=True,
            expected_column_names=("order_id", "amount"),
            expected_query_kinds=("show_relation_lookup", "show_relation_lookup", "show_columns"),
        ),
        SingleRelationLookupTestCase(
            description="session database qualifies an unqualified lookup",
            database=None,
            schema="staging",
            name="orders",
            expected_exists=True,
            expected_column_names=("order_id", "amount", "status", "rate", "ordered_at", "payload"),
            expected_query_kinds=("session", "show_relation_lookup", "show_columns"),
        ),
        SingleRelationLookupTestCase(
            description="LIKE wildcard neighbour is not an exact match",
            database="analytics",
            schema="staging",
            name="orders_delta",
            expected_exists=False,
            expected_column_names=(),
            expected_query_kinds=(
                "show_relation_lookup",
                "show_relation_lookup",
                "show_columns",
                "show_columns",
                "show_schemas",
            ),
        ),
        SingleRelationLookupTestCase(
            description="missing schema behaves as an absent relation",
            database="analytics",
            schema="fresh_target",
            name="orders",
            expected_exists=False,
            expected_column_names=(),
            expected_query_kinds=(
                "show_relation_lookup",
                "show_schemas",
                "show_relation_lookup",
                "show_schemas",
                "show_columns",
                "show_columns",
                "show_schemas",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_relation_when_looking_up_one_then_show_answers_without_information_schema(
    test_case: SingleRelationLookupTestCase,
) -> None:
    adapter: OfflineSnowflakeAdapter
    connection: _SnowflakeConnection
    warehouse: RecordingSnowflakeWarehouse
    adapter, connection, warehouse = build_offline_snowflake(relations=_RELATIONS)

    exists: bool = adapter.relation_exists(
        connection=connection,
        database=test_case.database,
        schema=test_case.schema,
        name=test_case.name,
    )
    columns: tuple[ColumnInfo, ...] = adapter.get_columns(
        connection=connection,
        database=test_case.database,
        schema=test_case.schema,
        name=test_case.name,
    )

    assert exists is test_case.expected_exists
    assert tuple(column.name for column in columns) == test_case.expected_column_names
    assert attempted_query_kinds(warehouse) == test_case.expected_query_kinds


@pytest.mark.parametrize(
    "test_case",
    [
        ShowColumnsEquivalenceTestCase(
            description=relation.name,
            database=relation.database.lower(),
            schema=relation.schema.lower(),
            name=relation.name.lower(),
            expected_column_count=len(relation.columns),
        )
        for relation in _RELATIONS
    ],
    ids=lambda case: case.description,
)
def test_given_relation_when_reading_columns_then_show_matches_information_schema(
    test_case: ShowColumnsEquivalenceTestCase,
) -> None:
    adapter: OfflineSnowflakeAdapter
    connection: _SnowflakeConnection
    adapter, connection, _ = build_offline_snowflake(relations=_RELATIONS)

    shown: tuple[ColumnInfo, ...] = adapter.get_columns(
        connection=connection,
        database=test_case.database,
        schema=test_case.schema,
        name=test_case.name,
    )
    legacy: tuple[ColumnInfo, ...] = adapter._information_schema_columns(
        connection=connection,
        database=test_case.database,
        schema=test_case.schema,
        name=test_case.name,
    )

    assert len(shown) == test_case.expected_column_count
    assert shown == legacy


@pytest.mark.parametrize(
    "test_case",
    [
        SingleRelationErrorTestCase(
            description="missing database fails instead of reporting an absent relation",
            database="retired",
            schema="staging",
            name="orders",
            expected_error_fragment="database retired does not exist",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_missing_database_when_looking_up_one_relation_then_raises_user_error(
    test_case: SingleRelationErrorTestCase,
) -> None:
    adapter: OfflineSnowflakeAdapter
    connection: _SnowflakeConnection
    adapter, connection, _ = build_offline_snowflake(relations=_RELATIONS)

    with pytest.raises(AdapterUserError, match=test_case.expected_error_fragment):
        _ = adapter.relation_exists(
            connection=connection,
            database=test_case.database,
            schema=test_case.schema,
            name=test_case.name,
        )
    with pytest.raises(AdapterUserError, match=test_case.expected_error_fragment):
        _ = adapter.get_columns(
            connection=connection,
            database=test_case.database,
            schema=test_case.schema,
            name=test_case.name,
        )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
