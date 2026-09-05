from __future__ import annotations

import pytest

from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.executor.run._helpers.validation.type_enforcement import (
    _build_type_enforcement_projection,
)
from tests.unit.src.sqlbuild.executor.run._helpers._test_types import (
    StagedTypeProjectionTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StagedTypeProjectionTestCase(
            description="snowflake projection quotes preserved and coerced columns",
            expected_sql='"HORSE ID", CAST("MODDS" AS TEXT) AS "MODDS"',
        )
    ],
    ids=lambda case: case.description,
)
def test_given_snowflake_columns_when_rendering_coercion_then_uses_adapter_identifiers(
    test_case: StagedTypeProjectionTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    result: str = _build_type_enforcement_projection(
        adapter=adapter,
        produced_columns=(
            ColumnInfo(name="horse id", type="NUMBER"),
            ColumnInfo(name="modds", type="FLOAT"),
        ),
        declared_map={"modds": "TEXT"},
    )

    assert result == test_case.expected_sql


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
