"""SQL-test helper CTE reads come from the native parse and match Python's `_parsed_reads`."""

from __future__ import annotations

import pytest

from tests.integration.src.sqlbuild.compiler.helpers import (
    GoldenEntry,
    golden_differences,
    golden_entry,
    golden_name,
    read_golden,
)
from tests.integration.src.sqlbuild.compiler.sql_test_glue._test_types import HelperReadsTestCase
from tests.integration.src.sqlbuild.compiler.sql_test_glue.helpers import helper_reads_view


@pytest.mark.parametrize(
    "test_case",
    [
        HelperReadsTestCase(
            description="helper cte read edges",
            keys=frozenset({"base", "helper", "mock_orders", "étapé"}),
            bodies=(
                "SELECT * FROM base",
                "SELECT * FROM BASE JOIN helper h ON 1=1 JOIN base b2 ON 1=1",
                "SELECT * FROM s.base JOIN db.s.helper ON 1=1",
                "WITH base AS (SELECT 1) SELECT * FROM base, helper",
                "SELECT * FROM (WITH Helper AS (SELECT 1) SELECT * FROM helper) x JOIN base ON 1=1",
                "SELECT 1",
                "SELECT * FROM unrelated",
                "SELECT * FROM base WHERE (",
                "SELECT * FROM ÉTAPÉ",
                'SELECT * FROM "Base"',
                "SELECT * FROM mock_orders UNION ALL SELECT * FROM helper WHERE id IN (SELECT id FROM base)",
                "SELECT base FROM other",
                "SELECT * FROM helper; SELECT * FROM base",
                "SELECT * FROM t WHERE EXISTS (SELECT 1 FROM helper)",
            ),
            expected_differences=[],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cte_bodies_when_reading_helper_keys_then_matches_python_golden(
    test_case: HelperReadsTestCase,
) -> None:
    views: list[tuple[str, ...] | None] = [
        helper_reads_view(body, test_case.keys) for body in test_case.bodies
    ]
    expected: list[GoldenEntry] = read_golden(golden_name("helper_reads", test_case.description))

    assert (
        golden_differences(expected, [golden_entry("helper_reads", view) for view in views])
        == test_case.expected_differences
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
