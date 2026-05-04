from __future__ import annotations

import pytest

import sqlbuild.adapter.shared.type_normalization as type_normalization
from sqlbuild.adapter.shared.type_normalization import (
    NormalizedType,
    TypeFamily,
    normalize_numeric_family,
    normalize_type,
    types_equal,
)
from tests.unit.src.sqlbuild.adapter.shared._test_types import (
    NumericFamilyTestCase,
    TypeEqualityTestCase,
    TypeNormalizationTestCase,
)

TYPE_NORMALIZATION_TEST_CASES: list[TypeNormalizationTestCase] = [
    TypeNormalizationTestCase(
        description="normalizes snowflake number precision and scale",
        dialect="snowflake",
        raw_type="NUMBER(38,0)",
        expected_type=NormalizedType(
            normalized_name="DECIMAL(38,0)",
            family=TypeFamily.DECIMAL,
            precision=38,
            scale=0,
        ),
    ),
    TypeNormalizationTestCase(
        description="normalizes bigquery int64 to integer family",
        dialect="bigquery",
        raw_type="INT64",
        expected_type=NormalizedType(normalized_name="INT64", family=TypeFamily.INTEGER),
    ),
    TypeNormalizationTestCase(
        description="normalizes bigquery string to normalized string family",
        dialect="bigquery",
        raw_type="STRING",
        expected_type=NormalizedType(normalized_name="STRING", family=TypeFamily.STRING),
    ),
]

FALLBACK_TYPE_NORMALIZATION_TEST_CASES: list[TypeNormalizationTestCase] = [
    TypeNormalizationTestCase(
        description="fallback normalizes bigquery integer alias",
        dialect="bigquery",
        raw_type="INTEGER",
        expected_type=NormalizedType(normalized_name="INT64", family=TypeFamily.INTEGER),
    ),
    TypeNormalizationTestCase(
        description="fallback preserves decimal precision and scale",
        dialect="snowflake",
        raw_type="NUMBER(10,2)",
        expected_type=NormalizedType(
            normalized_name="NUMBER(10,2)",
            family=TypeFamily.DECIMAL,
            precision=10,
            scale=2,
        ),
    ),
]

TYPE_EQUALITY_TEST_CASES: list[TypeEqualityTestCase] = [
    TypeEqualityTestCase(
        description="treats bigquery integer aliases as equal",
        dialect="bigquery",
        left_type="INT64",
        right_type="INTEGER",
        expected_equal=True,
    ),
    TypeEqualityTestCase(
        description="treats bigquery boolean aliases as equal",
        dialect="bigquery",
        left_type="BOOL",
        right_type="BOOLEAN",
        expected_equal=True,
    ),
    TypeEqualityTestCase(
        description="keeps snowflake varying string lengths distinct",
        dialect="snowflake",
        left_type="VARCHAR(16777216)",
        right_type="TEXT",
        expected_equal=False,
    ),
]

FALLBACK_TYPE_EQUALITY_TEST_CASES: list[TypeEqualityTestCase] = [
    TypeEqualityTestCase(
        description="fallback treats bigquery string aliases as equal",
        dialect="bigquery",
        left_type="STRING",
        right_type="TEXT",
        expected_equal=True,
    ),
    TypeEqualityTestCase(
        description="fallback keeps decimal scale differences distinct",
        dialect="snowflake",
        left_type="NUMBER(10,2)",
        right_type="NUMBER(10,3)",
        expected_equal=False,
    ),
]

NUMERIC_FAMILY_TEST_CASES: list[NumericFamilyTestCase] = [
    NumericFamilyTestCase(
        description="classifies bigquery integer alias as integer family",
        dialect="bigquery",
        raw_type="INTEGER",
        expected_family="integer",
    ),
    NumericFamilyTestCase(
        description="classifies snowflake number as decimal family",
        dialect="snowflake",
        raw_type="NUMBER(10,2)",
        expected_family="decimal",
    ),
    NumericFamilyTestCase(
        description="does not classify string as numeric",
        dialect="bigquery",
        raw_type="STRING",
        expected_family=None,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TYPE_NORMALIZATION_TEST_CASES,
    ids=[case.description for case in TYPE_NORMALIZATION_TEST_CASES],
)
def test_given_type_string_when_normalizing_then_it_returns_expected_shape(
    test_case: TypeNormalizationTestCase,
) -> None:
    result: NormalizedType = normalize_type(type_sql=test_case.raw_type, dialect=test_case.dialect)

    assert result == test_case.expected_type


@pytest.mark.parametrize(
    "test_case",
    FALLBACK_TYPE_NORMALIZATION_TEST_CASES,
    ids=[case.description for case in FALLBACK_TYPE_NORMALIZATION_TEST_CASES],
)
def test_given_type_string_when_normalizing_without_sqlglot_then_it_returns_expected_shape(
    test_case: TypeNormalizationTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(type_normalization, "_import_sqlglot", lambda: None)

    result: NormalizedType = normalize_type(type_sql=test_case.raw_type, dialect=test_case.dialect)

    assert result == test_case.expected_type


@pytest.mark.parametrize(
    "test_case",
    TYPE_EQUALITY_TEST_CASES,
    ids=[case.description for case in TYPE_EQUALITY_TEST_CASES],
)
def test_given_type_strings_when_comparing_then_it_returns_expected_equality(
    test_case: TypeEqualityTestCase,
) -> None:
    result: bool = types_equal(
        left=test_case.left_type,
        right=test_case.right_type,
        dialect=test_case.dialect,
    )

    assert result is test_case.expected_equal


@pytest.mark.parametrize(
    "test_case",
    FALLBACK_TYPE_EQUALITY_TEST_CASES,
    ids=[case.description for case in FALLBACK_TYPE_EQUALITY_TEST_CASES],
)
def test_given_type_strings_when_comparing_without_sqlglot_then_it_returns_expected_equality(
    test_case: TypeEqualityTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(type_normalization, "_import_sqlglot", lambda: None)

    result: bool = types_equal(
        left=test_case.left_type,
        right=test_case.right_type,
        dialect=test_case.dialect,
    )

    assert result is test_case.expected_equal


@pytest.mark.parametrize(
    "test_case",
    NUMERIC_FAMILY_TEST_CASES,
    ids=[case.description for case in NUMERIC_FAMILY_TEST_CASES],
)
def test_given_type_string_when_resolving_numeric_family_then_it_returns_expected_family(
    test_case: NumericFamilyTestCase,
) -> None:
    result: str | None = normalize_numeric_family(
        type_sql=test_case.raw_type,
        dialect=test_case.dialect,
    )

    assert result == test_case.expected_family


@pytest.mark.parametrize(
    "test_case",
    [
        NumericFamilyTestCase(
            description="fallback classifies float64 as float family",
            dialect="bigquery",
            raw_type="FLOAT64",
            expected_family="float",
        )
    ],
    ids=["fallback classifies float64 as float family"],
)
def test_given_type_string_without_sqlglot_when_resolving_numeric_family_then_it_returns_expected(
    test_case: NumericFamilyTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(type_normalization, "_import_sqlglot", lambda: None)

    result: str | None = normalize_numeric_family(
        type_sql=test_case.raw_type,
        dialect=test_case.dialect,
    )

    assert result == test_case.expected_family
