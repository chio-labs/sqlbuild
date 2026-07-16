from __future__ import annotations

import pytest

from sqlbuild.compiler.fingerprints.main.compute_query_hash import compute_query_hash
from sqlbuild.compiler.fingerprints.main.normalize_query_sql import normalize_query_sql
from tests.unit.src.sqlbuild.compiler.fingerprints.main._test_types import (
    ComputeQueryHashStabilityTestCase,
    ComputeQueryHashTestCase,
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
