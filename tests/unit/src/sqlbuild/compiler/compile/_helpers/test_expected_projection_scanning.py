"""Characterisation tests for the top-level scanners behind SQL-test expected projections."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile._helpers.sql_tests import core as sql_test_core
from sqlbuild.compiler.sql_analysis.main._split_set_operation_branches import (
    split_set_operation_branches,
)
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    ExpectedProjectionScanTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        ExpectedProjectionScanTestCase(
            description="plain select splits on top-level commas",
            sql="SELECT a, b AS c FROM orders",
            expected_branches=("SELECT a, b AS c FROM orders",),
            expected_select_list_end=len("SELECT a, b AS c "),
            expected_commas=("SELECT a", "b AS c FROM orders"),
            expected_alias=None,
            expected_contains_select_star=False,
        ),
        ExpectedProjectionScanTestCase(
            description="quotes and comments hide keywords, commas and parentheses",
            sql="SELECT 'x, FROM (' AS a, /* UNION , */ \"b)\" -- FROM\nFROM t",
            expected_branches=("SELECT 'x, FROM (' AS a, /* UNION , */ \"b)\" -- FROM\nFROM t",),
            expected_select_list_end=len("SELECT 'x, FROM (' AS a, /* UNION , */ \"b)\" -- FROM\n"),
            expected_commas=("SELECT 'x, FROM (' AS a", '/* UNION , */ "b)" -- FROM\nFROM t'),
            expected_alias=None,
            expected_contains_select_star=False,
        ),
        ExpectedProjectionScanTestCase(
            description="nested parentheses hide commas, FROM and AS",
            sql="SELECT f(a, (SELECT 1 AS x FROM y)) AS total",
            expected_branches=("SELECT f(a, (SELECT 1 AS x FROM y)) AS total",),
            expected_select_list_end=len("SELECT f(a, (SELECT 1 AS x FROM y)) AS total"),
            expected_commas=("SELECT f(a, (SELECT 1 AS x FROM y)) AS total",),
            expected_alias="total",
            expected_contains_select_star=False,
        ),
        ExpectedProjectionScanTestCase(
            description="union all splits branches",
            sql="SELECT 1 AS a UNION ALL SELECT 2 AS a",
            expected_branches=("SELECT 1 AS a", "SELECT 2 AS a"),
            expected_select_list_end=len("SELECT 1 AS a UNION ALL SELECT 2 AS a"),
            expected_commas=("SELECT 1 AS a UNION ALL SELECT 2 AS a",),
            expected_alias="a",
            expected_contains_select_star=False,
        ),
        ExpectedProjectionScanTestCase(
            description="union distinct splits branches",
            sql="SELECT 1 AS a UNION DISTINCT SELECT 2 AS a",
            expected_branches=("SELECT 1 AS a", "SELECT 2 AS a"),
            expected_select_list_end=len("SELECT 1 AS a UNION DISTINCT SELECT 2 AS a"),
            expected_commas=("SELECT 1 AS a UNION DISTINCT SELECT 2 AS a",),
            expected_alias="a",
            expected_contains_select_star=False,
        ),
        ExpectedProjectionScanTestCase(
            description="intersect and except split branches with quantifiers",
            sql="SELECT 1 AS a INTERSECT ALL SELECT 2 AS a EXCEPT DISTINCT SELECT 3 AS a",
            expected_branches=("SELECT 1 AS a", "SELECT 2 AS a", "SELECT 3 AS a"),
            expected_select_list_end=len(
                "SELECT 1 AS a INTERSECT ALL SELECT 2 AS a EXCEPT DISTINCT SELECT 3 AS a"
            ),
            expected_commas=(
                "SELECT 1 AS a INTERSECT ALL SELECT 2 AS a EXCEPT DISTINCT SELECT 3 AS a",
            ),
            expected_alias="a",
            expected_contains_select_star=False,
        ),
        ExpectedProjectionScanTestCase(
            description="star except modifier is not a set operation",
            sql="SELECT t.* EXCEPT (status), exceptional FROM t",
            expected_branches=("SELECT t.* EXCEPT (status), exceptional FROM t",),
            expected_select_list_end=len("SELECT t.* EXCEPT (status), exceptional "),
            expected_commas=("SELECT t.* EXCEPT (status)", "exceptional FROM t"),
            expected_alias=None,
            expected_contains_select_star=False,
        ),
        ExpectedProjectionScanTestCase(
            description="backtick identifiers are quoted",
            sql="SELECT `a, b` AS `c`, * FROM t",
            expected_branches=("SELECT `a, b` AS `c`, * FROM t",),
            expected_select_list_end=len("SELECT `a, b` AS `c`, * "),
            expected_commas=("SELECT `a, b` AS `c`", "* FROM t"),
            expected_alias=None,
            expected_contains_select_star=False,
        ),
        ExpectedProjectionScanTestCase(
            description="select star inside a subquery is detected",
            sql="SELECT a FROM (SELECT * FROM t)",
            expected_branches=("SELECT a FROM (SELECT * FROM t)",),
            expected_select_list_end=len("SELECT a "),
            expected_commas=("SELECT a FROM (SELECT * FROM t)",),
            expected_alias=None,
            expected_contains_select_star=True,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_expected_cte_sql_when_scanning_top_level_then_results_are_characterised(
    test_case: ExpectedProjectionScanTestCase,
) -> None:
    assert (
        split_set_operation_branches(sql=test_case.sql, context="SQL test")
        == test_case.expected_branches
    )
    assert (
        sql_test_core._find_select_list_end(sql=test_case.sql, start=0)
        == test_case.expected_select_list_end
    )
    assert sql_test_core._split_top_level_commas(test_case.sql) == test_case.expected_commas
    assert sql_test_core._extract_as_alias(test_case.sql) == test_case.expected_alias
    assert sql_test_core._contains_select_star(test_case.sql) is (
        test_case.expected_contains_select_star
    )
