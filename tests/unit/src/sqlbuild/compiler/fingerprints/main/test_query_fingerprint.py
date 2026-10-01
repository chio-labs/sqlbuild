from __future__ import annotations

import pytest

from sqlbuild.compiler.fingerprints.exceptions import QueryFingerprintError
from sqlbuild.compiler.fingerprints.main._normalize_query_sql import normalize_query_sql
from sqlbuild.compiler.fingerprints.main.compute_query_hash import compute_query_hash
from tests.unit.src.sqlbuild.compiler.fingerprints.main._test_types import (
    ComputeQueryHashStabilityTestCase,
    ComputeQueryHashTestCase,
    NormalizeQuerySqlTestCase,
    QueryFingerprintFailureTestCase,
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
            "generic token stream",
            None,
            "SELECT id, name FROM orders",
            "f85bdc364cd96495c98231d83cf8f7b3c81ed83c1fd5bcc4e1e774051df428b9",
        ),
        ComputeQueryHashTestCase(
            "DuckDB dollar quote and cast",
            "duckdb",
            "SELECT o.id, $$Customer's note$$ AS note, amount::DECIMAL(10, 2) AS amount "
            "FROM orders AS o",
            "c04892f1bd986fb6b2634b1dd23c81a47333b728d2ac49c986a07afc71eb2dcd",
        ),
        ComputeQueryHashTestCase(
            "PostgreSQL tagged dollar quote",
            "postgres",
            "SELECT o.id, $tag$it's$tag$ AS note, amount::NUMERIC AS amount FROM orders AS o",
            "d8e87b54443bdd072f761b460c8ebf04ec8d6a159388df8b84665ad4e50a0068",
        ),
        ComputeQueryHashTestCase(
            "Snowflake path access and QUALIFY",
            "snowflake",
            "SELECT o.id, payload:customer.name::STRING AS customer FROM orders AS o "
            "QUALIFY ROW_NUMBER() OVER (PARTITION BY o.id ORDER BY o.id) = 1",
            "382334949ddebe9982cb8f5a824d3ae38efccfc62365eff6127ed167d7a19f7a",
        ),
        ComputeQueryHashTestCase(
            "BigQuery raw string and backtick path",
            "bigquery",
            "SELECT o.id, r'raw\\d' AS pattern FROM `project.dataset.orders` AS o",
            "3f085456a0e426deac3d869a71e0ae4e3caaa195cf6c123fcecf5dd5d770f4a0",
        ),
        ComputeQueryHashTestCase(
            "Databricks optimizer hint",
            "databricks",
            "SELECT /*+ BROADCAST(o) */ o.id FROM `catalog`.`orders` AS o",
            "2e5fb997906d28955bc13c3f2d38b855bad5aee9f1244c48fec541796f2a96cf",
        ),
        ComputeQueryHashTestCase(
            "SQL Server bracket identifiers",
            "sqlserver",
            "SELECT TOP 10 [o].[id], N'order' AS kind FROM [dbo].[orders] AS o",
            "c04948e15a9f5561c284369d205e8971b2f3b7356f382859407004e9c0dd5676",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_dialect_query_when_computing_hash_then_golden_fingerprint_is_stable(
    test_case: ComputeQueryHashTestCase,
) -> None:
    result: str = compute_query_hash(query_sql=test_case.query_sql, dialect=test_case.dialect)

    assert result == test_case.expected_hash


@pytest.mark.parametrize(
    "test_case",
    [
        ComputeQueryHashStabilityTestCase(
            "whitespace and line breaks are ignored",
            "duckdb",
            "SELECT  id  FROM  orders",
            "select\n  id\nfrom orders",
            True,
        ),
        ComputeQueryHashStabilityTestCase(
            "comments are ignored",
            "snowflake",
            "SELECT id -- order key\nFROM orders /* all */",
            "SELECT id FROM orders",
            True,
        ),
        ComputeQueryHashStabilityTestCase(
            "unquoted keyword and identifier case is ignored",
            "duckdb",
            "SELECT Id FROM Orders",
            "select id from orders",
            True,
        ),
        ComputeQueryHashStabilityTestCase(
            "string literal whitespace is significant",
            "duckdb",
            "SELECT 'a  b' AS code",
            "SELECT 'a b' AS code",
            False,
        ),
        ComputeQueryHashStabilityTestCase(
            "quoted identifier case is significant",
            "snowflake",
            'SELECT "Id" FROM orders',
            'SELECT "ID" FROM orders',
            False,
        ),
        ComputeQueryHashStabilityTestCase(
            "number spelling is significant",
            "duckdb",
            "SELECT 1.0 AS amount",
            "SELECT 1.00 AS amount",
            False,
        ),
        ComputeQueryHashStabilityTestCase(
            "optimizer hints are significant",
            "databricks",
            "SELECT /*+ BROADCAST(o) */ o.id FROM orders o",
            "SELECT /*+ REPARTITION(3) */ o.id FROM orders o",
            False,
        ),
        ComputeQueryHashStabilityTestCase(
            "different queries produce different hashes",
            None,
            "SELECT id FROM orders",
            "SELECT id FROM customers",
            False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_two_queries_when_computing_hashes_then_stability_matches_expected(
    test_case: ComputeQueryHashStabilityTestCase,
) -> None:
    hash_a: str = compute_query_hash(query_sql=test_case.query_a, dialect=test_case.dialect)
    hash_b: str = compute_query_hash(query_sql=test_case.query_b, dialect=test_case.dialect)

    assert (hash_a == hash_b) == test_case.expected_same_hash


@pytest.mark.parametrize(
    "test_case",
    [
        QueryFingerprintFailureTestCase(
            "unterminated string literal",
            "duckdb",
            "SELECT 'open FROM orders",
            "Unterminated string",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_untokenizable_sql_when_computing_hash_then_raises_fingerprint_error(
    test_case: QueryFingerprintFailureTestCase,
) -> None:
    with pytest.raises(QueryFingerprintError, match=test_case.expected_message):
        _ = compute_query_hash(query_sql=test_case.query_sql, dialect=test_case.dialect)
