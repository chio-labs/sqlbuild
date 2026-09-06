from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pytest

from sqlbuild.compiler.compile._helpers.sql_tests import cache as cte_cache
from sqlbuild.compiler.compile._helpers.sql_tests.cache import cached_sql_test_cte_extractor
from sqlbuild.compiler.compile.models import CompileSqlTestCtes
from sqlbuild.compiler.compile.types import SqlTestMode
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    SqlTestCteCacheTestCase,
)

_TEST_SQL: str = (
    "WITH __ref__raw_orders AS (SELECT 1 AS order_id), "
    "__expected__orders AS (SELECT 1 AS order_id) SELECT 1"
)


@pytest.mark.parametrize(
    "test_case",
    (SqlTestCteCacheTestCase(description="unchanged SQL reuses CTEs", expected_scanner_calls=0),),
    ids=lambda case: case.description,
)
def test_given_cached_test_ctes_when_extracting_again_then_skips_scanner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_case: SqlTestCteCacheTestCase,
) -> None:
    with cached_sql_test_cte_extractor(root=tmp_path) as extract:
        expected: CompileSqlTestCtes = extract(_TEST_SQL, "test_orders.sql", SqlTestMode.MODEL)
    scanner: Mock = Mock(wraps=cte_cache.extract_unclassified_sql_test_ctes)
    monkeypatch.setattr(cte_cache, "extract_unclassified_sql_test_ctes", scanner)

    with cached_sql_test_cte_extractor(root=tmp_path) as extract:
        actual: CompileSqlTestCtes = extract(_TEST_SQL, "test_orders.sql", SqlTestMode.MODEL)

    assert scanner.call_count == test_case.expected_scanner_calls
    assert actual == expected


@pytest.mark.parametrize(
    "test_case",
    (SqlTestCteCacheTestCase(description="changed SQL scans CTEs", expected_scanner_calls=1),),
    ids=lambda case: case.description,
)
def test_given_changed_test_sql_when_extracting_then_scans_new_ctes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_case: SqlTestCteCacheTestCase,
) -> None:
    with cached_sql_test_cte_extractor(root=tmp_path) as extract:
        _ = extract(_TEST_SQL, "test_orders.sql", SqlTestMode.MODEL)
    scanner: Mock = Mock(wraps=cte_cache.extract_unclassified_sql_test_ctes)
    monkeypatch.setattr(cte_cache, "extract_unclassified_sql_test_ctes", scanner)
    changed_sql: str = _TEST_SQL.replace("SELECT 1 AS order_id", "SELECT 2 AS order_id")

    with cached_sql_test_cte_extractor(root=tmp_path) as extract:
        _ = extract(changed_sql, "test_orders.sql", SqlTestMode.MODEL)

    assert scanner.call_count == test_case.expected_scanner_calls


@pytest.mark.parametrize(
    "test_case",
    (SqlTestCteCacheTestCase(description="corrupt cache rescans", expected_scanner_calls=1),),
    ids=lambda case: case.description,
)
def test_given_corrupt_test_cte_cache_when_extracting_then_rescans_safely(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    test_case: SqlTestCteCacheTestCase,
) -> None:
    with cached_sql_test_cte_extractor(root=tmp_path) as extract:
        _ = extract(_TEST_SQL, "test_orders.sql", SqlTestMode.MODEL)
    cache_path: Path = next(tmp_path.rglob("sql-test-ctes.sqlite3"))
    with sqlite3.connect(cache_path) as connection:
        _ = connection.execute("UPDATE sql_test_cte SET payload = 'broken'")
    scanner: Mock = Mock(wraps=cte_cache.extract_unclassified_sql_test_ctes)
    monkeypatch.setattr(cte_cache, "extract_unclassified_sql_test_ctes", scanner)

    with cached_sql_test_cte_extractor(root=tmp_path) as extract:
        _ = extract(_TEST_SQL, "test_orders.sql", SqlTestMode.MODEL)

    assert scanner.call_count == test_case.expected_scanner_calls
