from __future__ import annotations

import pytest

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.shared.helpers.identity.hashing import (
    compute_query_hash,
    compute_schema_fingerprint,
    normalize_query_sql,
)
from tests.unit.src.sqlbuild.shared.helpers.identity._test_types import (
    ComputeQueryHashStabilityTestCase,
    ComputeQueryHashTestCase,
    ComputeSchemaFingerprintStabilityTestCase,
    ComputeSchemaFingerprintTestCase,
    NormalizeQuerySqlTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        NormalizeQuerySqlTestCase(
            description="strips leading and trailing whitespace",
            query_sql="  SELECT id FROM orders  ",
            expected_normalized="SELECT id FROM orders",
        ),
        NormalizeQuerySqlTestCase(
            description="collapses internal whitespace runs to single spaces",
            query_sql="SELECT  id,  name\n  FROM\n    orders",
            expected_normalized="SELECT id, name FROM orders",
        ),
        NormalizeQuerySqlTestCase(
            description="preserves casing exactly",
            query_sql="SELECT Id FROM Orders WHERE Status = 'Active'",
            expected_normalized="SELECT Id FROM Orders WHERE Status = 'Active'",
        ),
        NormalizeQuerySqlTestCase(
            description="handles tabs and carriage returns",
            query_sql="\tSELECT\t\tid\r\nFROM orders\t",
            expected_normalized="SELECT id FROM orders",
        ),
        NormalizeQuerySqlTestCase(
            description="returns empty string for whitespace-only input",
            query_sql="   \n\t  ",
            expected_normalized="",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_raw_query_when_normalizing_then_returns_expected_text(
    test_case: NormalizeQuerySqlTestCase,
) -> None:
    result: str = normalize_query_sql(test_case.query_sql)

    assert result == test_case.expected_normalized


@pytest.mark.parametrize(
    "test_case",
    [
        ComputeQueryHashTestCase(
            description="produces sha256 hex digest for simple query",
            query_sql="SELECT id, name FROM orders",
            expected_hash="c87cdf54b562650a0cc936e8c4243e32513acc37fe42527c19c1a3421c9c105c",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_query_sql_when_computing_hash_then_returns_expected_digest(
    test_case: ComputeQueryHashTestCase,
) -> None:
    result: str = compute_query_hash(test_case.query_sql)

    assert result == test_case.expected_hash


@pytest.mark.parametrize(
    "test_case",
    [
        ComputeQueryHashStabilityTestCase(
            description="whitespace-only differences produce the same hash",
            query_a="SELECT  id  FROM  orders",
            query_b="SELECT id FROM orders",
            expected_same_hash=True,
        ),
        ComputeQueryHashStabilityTestCase(
            description="casing differences produce different hashes",
            query_a="SELECT id FROM orders",
            query_b="select id from orders",
            expected_same_hash=False,
        ),
        ComputeQueryHashStabilityTestCase(
            description="different queries produce different hashes",
            query_a="SELECT id FROM orders",
            query_b="SELECT id FROM customers",
            expected_same_hash=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_two_queries_when_computing_hashes_then_stability_matches_expected(
    test_case: ComputeQueryHashStabilityTestCase,
) -> None:
    hash_a: str = compute_query_hash(test_case.query_a)
    hash_b: str = compute_query_hash(test_case.query_b)

    assert (hash_a == hash_b) == test_case.expected_same_hash


@pytest.mark.parametrize(
    "test_case",
    [
        ComputeSchemaFingerprintTestCase(
            description="produces sha256 hex digest for column schema",
            columns=(
                ColumnInfo(name="id", type="INTEGER"),
                ColumnInfo(name="name", type="VARCHAR"),
            ),
            expected_fingerprint=(
                "f25d3e78415cea0d129068b893ef685387bf801d5d12ecad07ff0a3d2ef70d6c"
            ),
        ),
        ComputeSchemaFingerprintTestCase(
            description="produces deterministic hash for empty columns",
            columns=(),
            expected_fingerprint=(
                "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_columns_when_computing_schema_fingerprint_then_returns_expected_digest(
    test_case: ComputeSchemaFingerprintTestCase,
) -> None:
    result: str = compute_schema_fingerprint(test_case.columns)

    assert result == test_case.expected_fingerprint


@pytest.mark.parametrize(
    "test_case",
    [
        ComputeSchemaFingerprintStabilityTestCase(
            description="different column order produces different fingerprints",
            columns_a=(
                ColumnInfo(name="id", type="INTEGER"),
                ColumnInfo(name="name", type="VARCHAR"),
            ),
            columns_b=(
                ColumnInfo(name="name", type="VARCHAR"),
                ColumnInfo(name="id", type="INTEGER"),
            ),
            expected_same_fingerprint=False,
        ),
        ComputeSchemaFingerprintStabilityTestCase(
            description="type change produces different fingerprints",
            columns_a=(ColumnInfo(name="id", type="INTEGER"),),
            columns_b=(ColumnInfo(name="id", type="BIGINT"),),
            expected_same_fingerprint=False,
        ),
        ComputeSchemaFingerprintStabilityTestCase(
            description="identical columns produce the same fingerprint",
            columns_a=(
                ColumnInfo(name="id", type="INTEGER"),
                ColumnInfo(name="name", type="VARCHAR"),
            ),
            columns_b=(
                ColumnInfo(name="id", type="INTEGER"),
                ColumnInfo(name="name", type="VARCHAR"),
            ),
            expected_same_fingerprint=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_two_column_sets_when_computing_fingerprints_then_stability_matches_expected(
    test_case: ComputeSchemaFingerprintStabilityTestCase,
) -> None:
    fp_a: str = compute_schema_fingerprint(test_case.columns_a)
    fp_b: str = compute_schema_fingerprint(test_case.columns_b)

    assert (fp_a == fp_b) == test_case.expected_same_fingerprint
