"""Native type normalization defers every type to Python until the native type system lands."""

from __future__ import annotations

import pytest

from sqlbuild.adapter.type_system.main._native_normalize_type import normalize_native_type
from tests.unit.src.sqlbuild.adapter.type_system._test_types import (
    NativeTypeNormalizationTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        NativeTypeNormalizationTestCase(
            description="snowflake number",
            dialect="snowflake",
            raw_type="NUMBER(38,0)",
            expected_type=None,
        ),
        NativeTypeNormalizationTestCase(
            description="duckdb sized varchar",
            dialect="duckdb",
            raw_type="VARCHAR(20)",
            expected_type=None,
        ),
        NativeTypeNormalizationTestCase(
            description="no dialect",
            dialect=None,
            raw_type="TIMESTAMP WITH TIME ZONE",
            expected_type=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_type_string_when_normalizing_natively_then_it_defers_to_python(
    test_case: NativeTypeNormalizationTestCase,
) -> None:
    assert (
        normalize_native_type(type_sql=test_case.raw_type, dialect=test_case.dialect)
        == test_case.expected_type
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
