"""Characterisation tests for the top-level scanners behind SQL-test expected projections."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile._helpers.sql_tests import core as sql_test_core
from sqlbuild.compiler.sql_analysis.main._split_set_operation_branches import (
    split_set_operation_branches,
)
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    DialectSetOperationSplitTestCase,
    ExpectedProjectionScanTestCase,
)

_GENERIC_SQL_SYNTAX: SqlLexicalSyntax = SqlLexicalSyntax()


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
            description="comments around branches and projections are not code",
            sql="-- lead\nSELECT 1 AS a /* one */\n-- before\nUNION ALL /* after */ SELECT '--' AS a -- end",
            expected_branches=("SELECT 1 AS a", "SELECT '--' AS a"),
            expected_select_list_end=len(
                "-- lead\nSELECT 1 AS a /* one */\n-- before\nUNION ALL /* after */ SELECT '--' AS a -- end"
            ),
            expected_commas=(
                "-- lead\nSELECT 1 AS a /* one */\n-- before\nUNION ALL /* after */ SELECT '--' AS a -- end",
            ),
            expected_alias="a",
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
        sql_test_core._find_select_list_end(sql=test_case.sql, start=0, syntax=_GENERIC_SQL_SYNTAX)
        == test_case.expected_select_list_end
    )
    assert (
        sql_test_core._split_top_level_commas(raw_value=test_case.sql, syntax=_GENERIC_SQL_SYNTAX)
        == test_case.expected_commas
    )
    assert (
        sql_test_core._extract_as_alias(expression=test_case.sql, syntax=_GENERIC_SQL_SYNTAX)
        == test_case.expected_alias
    )
    assert sql_test_core._contains_select_star(sql=test_case.sql, syntax=_GENERIC_SQL_SYNTAX) is (
        test_case.expected_contains_select_star
    )


@pytest.mark.parametrize(
    "test_case",
    (
        DialectSetOperationSplitTestCase(
            description="generic rules end a block comment at the first close",
            sql="SELECT 1 AS a /* x /* UNION ALL */ SELECT 9 AS b */ UNION ALL SELECT 2 AS a",
            syntax=None,
            expected_branches=(
                "SELECT 1 AS a /* x /* UNION ALL */ SELECT 9 AS b */",
                "SELECT 2 AS a",
            ),
        ),
        DialectSetOperationSplitTestCase(
            description="nested block comments hide a set operation",
            sql="SELECT 1 AS a /* x /* UNION ALL */ SELECT 9 AS b */ UNION ALL SELECT 2 AS a",
            syntax=SqlLexicalSyntax(nested_block_comments=True),
            expected_branches=("SELECT 1 AS a", "SELECT 2 AS a"),
        ),
        DialectSetOperationSplitTestCase(
            description="dialect line comment prefixes hide a set operation",
            sql="SELECT 1 AS a # UNION ALL SELECT 9 AS b\nUNION ALL SELECT 2 AS a # end",
            syntax=SqlLexicalSyntax(line_comment_prefixes=frozenset({"--", "#"})),
            expected_branches=("SELECT 1 AS a", "SELECT 2 AS a"),
        ),
        DialectSetOperationSplitTestCase(
            description="backslash escapes keep a quote open",
            sql="SELECT 'it\\' UNION ALL SELECT 9' AS a UNION ALL SELECT 'x' AS a",
            syntax=SqlLexicalSyntax(backslash_escape_quotes=frozenset({"'"})),
            expected_branches=("SELECT 'it\\' UNION ALL SELECT 9' AS a", "SELECT 'x' AS a"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_dialect_lexical_syntax_when_splitting_set_operations_then_follows_dialect_rules(
    test_case: DialectSetOperationSplitTestCase,
) -> None:
    assert (
        split_set_operation_branches(sql=test_case.sql, context="SQL test", syntax=test_case.syntax)
        == test_case.expected_branches
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
