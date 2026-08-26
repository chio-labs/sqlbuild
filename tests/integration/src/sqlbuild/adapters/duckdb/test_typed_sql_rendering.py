from decimal import Decimal

import duckdb
import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.sql_values.main.normalize import normalize_sql_value
from tests.integration.src.sqlbuild.adapters.duckdb._test_types import (
    TypedSqlRenderingExecutionTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        TypedSqlRenderingExecutionTestCase(
            description="value list array and object execute with typed semantics",
            expected_row=(True, "FR", "O'Brien", Decimal("2.4700")),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_typed_values_when_executing_duckdb_rendering_then_values_round_trip(
    test_case: TypedSqlRenderingExecutionTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    value_list: str = adapter.render_typed_value_list(
        value=normalize_sql_value(raw_value=["GB", "FR"], context="countries")
    )
    array: str = adapter.render_typed_array(
        value=normalize_sql_value(raw_value=["GB", "FR"], context="countries")
    )
    object_value: str = adapter.render_typed_object(
        value=normalize_sql_value(
            raw_value={"label": "O'Brien", "rate": Decimal("2.4700")},
            context="rules",
        )
    )
    sql: str = (
        f"SELECT 'GB' IN {value_list}, {array}[2], "
        f"json_extract_string({object_value}, '$.label'), "
        f"CAST(json_extract_string({object_value}, '$.rate') AS DECIMAL(10, 4))"
    )

    with duckdb.connect() as connection:
        row: tuple[object, ...] | None = connection.execute(sql).fetchone()

    assert row == test_case.expected_row


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
