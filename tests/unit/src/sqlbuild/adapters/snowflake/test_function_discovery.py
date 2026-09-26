"""Function discovery must address the requested catalog independently of session state."""

from typing import Any, cast

import pytest

from sqlbuild.adapter.contract.models import FunctionInfo
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from tests.unit.src.sqlbuild.adapters.snowflake._test_types import (
    SnowflakeFunctionDiscoveryTestCase,
)
from tests.unit.src.sqlbuild.adapters.snowflake.helpers import (
    FakeSnowflakeMetadataConnection,
    FakeSnowflakeMetadataCursor,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeFunctionDiscoveryTestCase(
            description="explicit database qualifies the information schema",
            database="analytics",
            schemas=("public",),
            names=("normalize_order",),
            rows=(("NORMALIZE_ORDER", "PUBLIC", "function"),),
            expected_relation='FROM "ANALYTICS".information_schema.functions',
            expected_params=("PUBLIC", "NORMALIZE_ORDER", "analytics"),
            expected_functions=(
                FunctionInfo(
                    database="analytics",
                    schema="public",
                    name="normalize_order",
                    function_type="function",
                ),
            ),
        ),
        SnowflakeFunctionDiscoveryTestCase(
            description="database containing a quote is escaped",
            database='order"catalog',
            schemas=None,
            names=None,
            rows=(),
            expected_relation='FROM "ORDER""CATALOG".information_schema.functions',
            expected_params=('order"catalog',),
            expected_functions=(),
        ),
        SnowflakeFunctionDiscoveryTestCase(
            description="omitted database uses the session catalog",
            database=None,
            schemas=None,
            names=None,
            rows=(),
            expected_relation="FROM information_schema.functions",
            expected_params=(),
            expected_functions=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_database_when_listing_functions_then_queries_matching_catalog(
    test_case: SnowflakeFunctionDiscoveryTestCase,
) -> None:
    cursor: FakeSnowflakeMetadataCursor = FakeSnowflakeMetadataCursor(rows=list(test_case.rows))

    result: tuple[FunctionInfo, ...] = SnowflakeAdapter().list_functions(
        connection=cast(Any, FakeSnowflakeMetadataConnection(cursor)),
        database=test_case.database,
        schemas=test_case.schemas,
        names=test_case.names,
    )

    assert test_case.expected_relation in str(cursor.executed_sql)
    assert cursor.executed_params == test_case.expected_params
    assert result == test_case.expected_functions
    assert cursor.closed


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
