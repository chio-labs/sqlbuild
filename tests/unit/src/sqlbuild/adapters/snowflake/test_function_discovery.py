"""Function discovery must address the requested catalog independently of session state."""

from typing import Any, cast

import pytest

from sqlbuild.adapter.contract.models import FunctionInfo
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from tests.unit.src.sqlbuild.adapters.snowflake.helpers import (
    FakeSnowflakeMetadataConnection,
    FakeSnowflakeMetadataCursor,
)


def test_given_explicit_database_when_listing_functions_then_queries_requested_catalog() -> None:
    cursor = FakeSnowflakeMetadataCursor(rows=[("NORMALIZE_ORDER", "PUBLIC", "function")])
    connection = FakeSnowflakeMetadataConnection(cursor)

    result = SnowflakeAdapter().list_functions(
        connection=cast(Any, connection),
        database="analytics",
        schemas=("public",),
        names=("normalize_order",),
    )

    assert cursor.executed_sql is not None
    assert 'FROM "ANALYTICS".information_schema.functions' in cursor.executed_sql
    assert cursor.executed_params == ("PUBLIC", "NORMALIZE_ORDER", "analytics")
    assert result == (
        FunctionInfo(
            database="analytics",
            schema="public",
            name="normalize_order",
            function_type="function",
        ),
    )
    assert cursor.closed


def test_given_database_with_quote_when_listing_functions_then_escapes_identifier() -> None:
    cursor = FakeSnowflakeMetadataCursor()

    SnowflakeAdapter().list_functions(
        connection=cast(Any, FakeSnowflakeMetadataConnection(cursor)),
        database='order"catalog',
        schemas=None,
    )

    assert cursor.executed_sql is not None
    assert 'FROM "ORDER""CATALOG".information_schema.functions' in cursor.executed_sql
    assert cursor.closed


def test_given_no_database_when_listing_functions_then_uses_session_catalog() -> None:
    cursor = FakeSnowflakeMetadataCursor()

    result = SnowflakeAdapter().list_functions(
        connection=cast(Any, FakeSnowflakeMetadataConnection(cursor)),
        database=None,
        schemas=None,
    )

    assert cursor.executed_sql is not None
    assert "FROM information_schema.functions" in cursor.executed_sql
    assert cursor.executed_params == ()
    assert result == ()
    assert cursor.closed


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
