"""Native type normalization matches Python for every type it answers, or defers."""

from __future__ import annotations

import random

import pytest

from sqlbuild.adapter.type_system.main._native_normalize_type import normalize_native_type
from tests.integration.src.sqlbuild.adapter.type_system._test_types import (
    DeepTypeTestCase,
    GeneratedTypeParityTestCase,
    TypeParityTestCase,
)
from tests.integration.src.sqlbuild.adapter.type_system.helpers import (
    TypeParity,
    generated_type,
    is_native,
    logged_parse_error,
    type_parities,
)
from tests.integration.src.sqlbuild.compiler.helpers import mismatches

_NATIVE_DIALECTS: frozenset[str | None] = frozenset(
    {None, "generic", "bigquery", "snowflake", "duckdb", "databricks", "postgres", "tsql"}
    | {"postgresql", "DuckDB"}
)


@pytest.mark.parametrize(
    "test_case",
    [
        GeneratedTypeParityTestCase(
            description="seeded scalar, parameterized, nested, padded and invalid types",
            seed=20261008,
            count=1500,
            expected_minimum_native=12000,
            expected_minimum_parse_errors=5000,
            expected_minimum_deferred=3000,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_types_when_normalizing_natively_then_python_normalization_matches(
    test_case: GeneratedTypeParityTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    type_strings: list[str] = [generated_type(rng=rng) for _ in range(test_case.count)]
    parities: list[TypeParity] = type_parities(type_strings=type_strings, monkeypatch=monkeypatch)

    answered: list[TypeParity] = list(filter(is_native, parities))
    assert (
        mismatches(
            inputs=[(parity.type_sql, parity.dialect) for parity in answered],
            expected=[parity.python for parity in answered],
            actual=[parity.native for parity in answered],
        ),
        len(answered) >= test_case.expected_minimum_native,
        sum(map(logged_parse_error, answered)) >= test_case.expected_minimum_parse_errors,
        len(parities) - len(answered) >= test_case.expected_minimum_deferred,
    ) == ([], True, True, True), test_case.description


@pytest.mark.parametrize(
    "test_case",
    [
        TypeParityTestCase(
            description="integer aliases",
            type_sql="INTEGER",
            expected_native_dialects=_NATIVE_DIALECTS,
        ),
        TypeParityTestCase(
            description="snowflake number precision and scale defaults",
            type_sql="NUMBER",
            expected_native_dialects=_NATIVE_DIALECTS,
        ),
        TypeParityTestCase(
            description="spaced decimal parameters",
            type_sql=" decimal( 10 , 2 ) ",
            expected_native_dialects=_NATIVE_DIALECTS,
        ),
        TypeParityTestCase(
            description="unbounded text",
            type_sql="TEXT",
            expected_native_dialects=_NATIVE_DIALECTS,
        ),
        TypeParityTestCase(
            description="nested array of structs",
            type_sql="ARRAY<STRUCT<order_id INT, tags ARRAY<STRING>>>",
            expected_native_dialects=_NATIVE_DIALECTS,
        ),
        TypeParityTestCase(
            description="map of varchar to decimal",
            type_sql="MAP(VARCHAR, DECIMAL(18, 4))",
            expected_native_dialects=_NATIVE_DIALECTS,
        ),
        TypeParityTestCase(
            description="quoted custom type",
            type_sql='"Order Status"',
            expected_native_dialects=_NATIVE_DIALECTS,
        ),
        TypeParityTestCase(
            description="timestamp aliases",
            type_sql="timestamp_ntz(9)",
            expected_native_dialects=_NATIVE_DIALECTS,
        ),
        TypeParityTestCase(
            description="invalid type falls back after a logged parse error",
            type_sql="order status",
            expected_native_dialects=_NATIVE_DIALECTS,
        ),
        TypeParityTestCase(
            description="parameters Python keeps as large integers defer",
            type_sql="VARCHAR(99999999999999999999)",
            expected_native_dialects=frozenset(),
        ),
        TypeParityTestCase(
            description="array suffixes at the bracket cap",
            type_sql="INT" + "[]" * 32,
            expected_native_dialects=_NATIVE_DIALECTS,
        ),
        TypeParityTestCase(
            description="array suffixes past the bracket cap defer",
            type_sql="INT" + "[]" * 33,
            expected_native_dialects=frozenset(),
        ),
        TypeParityTestCase(
            description="non-ASCII text defers",
            type_sql="caf\u00e9",
            expected_native_dialects=frozenset(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_type_when_normalizing_under_each_dialect_then_native_answers_match_python(
    test_case: TypeParityTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    parities: list[TypeParity] = type_parities(
        type_strings=[test_case.type_sql], monkeypatch=monkeypatch
    )

    answered: list[TypeParity] = list(filter(is_native, parities))
    assert (
        mismatches(
            inputs=[parity.dialect for parity in answered],
            expected=[parity.python for parity in answered],
            actual=[parity.native for parity in answered],
        ),
        frozenset(parity.dialect for parity in answered),
    ) == ([], test_case.expected_native_dialects), test_case.description


@pytest.mark.parametrize(
    "test_case",
    [
        DeepTypeTestCase(
            description="100,000 array suffixes, past where the wheel itself overflows",
            type_sql="INT" + "[]" * 100_000,
            expected_native=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_type_past_the_wheel_depth_when_normalizing_natively_then_it_defers(
    test_case: DeepTypeTestCase,
) -> None:
    assert normalize_native_type(type_sql=test_case.type_sql, dialect="generic") is (
        test_case.expected_native
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
