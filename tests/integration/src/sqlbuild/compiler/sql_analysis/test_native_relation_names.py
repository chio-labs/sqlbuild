"""Hard-coded relation names come from the native parse and match Python's dict walk."""

from __future__ import annotations

import pytest

from tests.integration.src.sqlbuild.compiler.helpers import (
    GoldenEntry,
    golden_differences,
    golden_entry,
    golden_name,
    read_golden,
)
from tests.integration.src.sqlbuild.compiler.sql_analysis._test_types import (
    RelationNamesTestCase,
)
from tests.integration.src.sqlbuild.compiler.sql_analysis.helpers import relation_names_outcome


@pytest.mark.parametrize(
    "test_case",
    [
        RelationNamesTestCase(
            description="hard coded relation edges",
            queries=(
                ("SELECT * FROM orders", None),
                (
                    "SELECT * FROM analytics.orders o JOIN db.sales.customers c ON o.id = c.id",
                    "duckdb",
                ),
                (
                    "WITH Recent AS (SELECT * FROM orders) SELECT * FROM recent JOIN RECENT r2 ON 1=1",
                    "duckdb",
                ),
                ("WITH recent AS (SELECT 1) SELECT * FROM s.recent", "duckdb"),
                (
                    "CREATE TEMPORARY TABLE Staging AS SELECT * FROM raw.events; INSERT INTO staging SELECT * FROM raw.events",
                    "duckdb",
                ),
                ("CREATE TEMP TABLE t1 (id INT); SELECT * FROM T1", "postgres"),
                ("SELECT * FROM `proj.dataset.table` JOIN `a.b` USING (id)", "bigquery"),
                ('SELECT * FROM "Weird.Name"', "duckdb"),
                ("SELECT * FROM a.b.c.d", "duckdb"),
                ("SELECT (", "duckdb"),
                ("", "duckdb"),
                ("SELECT 1; SELECT * FROM x; SELECT * FROM x", ""),
                ("UPDATE inventory SET qty = 0 WHERE id IN (SELECT id FROM products)", "snowflake"),
                (
                    "DELETE FROM sales.orders USING customers WHERE orders.cid = customers.id",
                    "postgres",
                ),
                (
                    "MERGE INTO tgt USING src ON tgt.id = src.id WHEN MATCHED THEN UPDATE SET v = src.v",
                    "snowflake",
                ),
                ("SELECT * FROM [dbo].[Orders]", "sqlserver"),
                ("SELECT * FROM Größe, ÉTÉ", "duckdb"),
                ("WITH ÉTÉ AS (SELECT 1) SELECT * FROM été", "duckdb"),
                ("CREATE TABLE perm AS SELECT 1", "duckdb"),
                ("SELECT * FROM orders", "motherduck"),
                ("SELECT * FROM read_csv('x.csv'), generate_series(1, 3)", "duckdb"),
                (
                    "SELECT * FROM t1 WHERE EXISTS (SELECT 1 FROM t2 WHERE t2.id = t1.id) UNION SELECT * FROM t3",
                    "databricks",
                ),
            ),
            expected_differences=[],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_python_node_sql_when_extracting_relation_names_then_matches_python_golden(
    test_case: RelationNamesTestCase,
) -> None:
    outcomes: list[object] = [
        relation_names_outcome(sql, dialect) for sql, dialect in test_case.queries
    ]
    expected: list[GoldenEntry] = read_golden(golden_name("relation_names", test_case.description))

    assert (
        golden_differences(expected, [golden_entry("relation_names", item) for item in outcomes])
        == test_case.expected_differences
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
