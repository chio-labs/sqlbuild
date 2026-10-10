"""Fixture projection facts match Python's `_simple_projection_facts` recorded in a golden."""

from __future__ import annotations

import pytest

import sqlbuild._native as native_module
from tests.integration.src.sqlbuild.compiler.analysis_session._test_types import (
    ProjectionFactsTestCase,
)
from tests.integration.src.sqlbuild.compiler.analysis_session.helpers import projection_view
from tests.integration.src.sqlbuild.compiler.helpers import (
    GoldenEntry,
    golden_differences,
    golden_entry,
    golden_name,
    read_golden,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ProjectionFactsTestCase(
            description="fixture projection edges",
            queries=(
                ("SELECT 'a' AS name, 1 AS qty, TRUE AS flag, NULL AS missing", "duckdb"),
                (
                    "SELECT ARRAY_CONSTRUCT(1, 2) AS items, OBJECT_CONSTRUCT('a', 1) AS obj, PARSE_JSON('{}') AS doc, [1, 2] AS arr",
                    "snowflake",
                ),
                ('SELECT NULL AS "Quoted", \'x\' AS "Größe", 2 AS STRASSE', "duckdb"),
                (
                    "WITH base AS (SELECT NULL AS gone, 'v' AS kept) SELECT gone, kept FROM base",
                    "duckdb",
                ),
                ("SELECT * FROM (SELECT NULL AS inner_null, 1.5 AS ratio) AS t", "duckdb"),
                ("SELECT 'a' AS x UNION ALL SELECT NULL AS x", "duckdb"),
                ("SELECT lower('A') AS lowered, CAST(1 AS INT) AS cast_one, 'ß' AS ß", "duckdb"),
                ("SELECT 1 AS a, 'dup' AS a", "generic"),
                ("SELECT parse_json('[1]') AS p, STRUCT_PACK(a := 1) AS s", "duckdb"),
                ("SELECT ( AS broken", "duckdb"),
                ("SELECT 1 AS one; SELECT 2 AS two", "duckdb"),
                ("SELECT {'a': 1} AS st, NULL AS n", "duckdb"),
                ("INSERT INTO t SELECT NULL AS n, 'a' AS s", "duckdb"),
                ('SELECT \'é\' AS "ÉTÉ", null AS "İ"', "bigquery"),
                ("SELECT 1 AS id", "postgres"),
                ("SELECT 'a' AS k", "tsql"),
            ),
            expected_differences=[],
        )
    ],
    ids=lambda case: case.description,
)
def test_given_fixture_queries_when_reading_projection_facts_then_matches_python_golden(
    test_case: ProjectionFactsTestCase,
) -> None:
    views: list[tuple[dict[str, str], frozenset[str], frozenset[str]]] = [
        projection_view(native_module.fixture_projection_facts(sql, dialect))
        for sql, dialect in test_case.queries
    ]
    expected: list[GoldenEntry] = read_golden(
        golden_name("projection_facts", test_case.description)
    )

    assert (
        golden_differences(expected, [golden_entry("projection_facts", view) for view in views])
        == test_case.expected_differences
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
