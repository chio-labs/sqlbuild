"""Native reference extraction: references, rejected calls and scan bounds."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import pytest

import sqlbuild._native as _native
from sqlbuild.compiler.compile._helpers.refs.references import extract_sql_references
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from tests.integration.src.sqlbuild.compiler.compile._helpers.refs._test_types import (
    CraftedReferenceTestCase,
    ReferenceExtractionTestCase,
    ReferenceScanBoundTestCase,
)

_GENERIC_SYNTAX: SqlLexicalSyntax = SqlLexicalSyntax()
_REFERENCE_SQLS: tuple[
    tuple[str, str, tuple[tuple[str, str, str | None, int | None], ...], str], ...
] = (
    (
        "table_function",
        'SELECT * FROM __table_fn("orders_for")(1, 2) JOIN __ref("customers")',
        (("table_fn", "orders_for", None, 2), ("ref", "customers", None, None)),
        "",
    ),
    (
        "rejected_call",
        "SELECT * FROM __ref(orders, customers)",
        (),
        "__ref(orders, customers) is not a valid __ref() call",
    ),
    (
        "unclosed_call",
        'SELECT * FROM __ref("orders"',
        (),
        "SQL reference contains an unclosed parenthesis",
    ),
)

_MANY_CALLS: str = "SELECT 1 FROM " + " JOIN ".join(
    f'__table_fn("orders_for")({index}, \'a,b\', (1, 2)) JOIN __ref("orders_{index}")'
    for index in range(5_000)
)
_WIDE_CALL: str = (
    '__table_fn("orders_for")(' + ", ".join(f"(c{index} /* , */)" for index in range(100_000)) + ")"
)
_NESTED_CALLS: str = '__table_fn("orders_for")(' * 1_000 + "1" + ")" * 1_000
_SCANNER: _native.SqlReferenceScanner = _native.SqlReferenceScanner(_GENERIC_SYNTAX.native_mapping)
_OUTCOME_SUMMARIES: dict[type, Callable[[Any], int | str]] = {
    tuple: lambda outcome: len(outcome[0][0]) + len(outcome[0][1]),
    type(None): lambda outcome: outcome[1][0],
}
_REJECTED_AND_FAILED: dict[type, Callable[[Any], tuple[int, int]]] = {
    tuple: lambda outcome: (len(outcome[0][1]), 0),
    type(None): lambda _outcome: (0, 1),
}
_MANY_REFERENCES: str = "SELECT 1 FROM " + " JOIN ".join(
    f'__ref("orders_{index}")' for index in range(50_000)
)
_ERROR_AFTER_MANY: str = _MANY_REFERENCES + ' JOIN __ref("orders"'
_REJECTED_AFTER_MANY: str = _MANY_REFERENCES + " JOIN __ref(orders, customers)"


@pytest.mark.parametrize(
    "test_case",
    [
        CraftedReferenceTestCase(
            description="every_kind_in_authored_order",
            sql=(
                'SELECT * FROM __ref("orders") JOIN __source("raw_orders") '
                'JOIN __seed("regions") JOIN __dbt_ref("shop" ,\u3000"customers") '
                'WHERE __udf("clean")(x) > 0 OR __dbt_ref("orders") IS NULL'
            ),
        ),
        CraftedReferenceTestCase(
            description="table_function_argument_counts",
            sql=(
                "SELECT * FROM __table_fn(\"expand_orders\") ( 1, f(2, 3), 'a,b' /* , */ ) "
                'JOIN __table_fn("daily_orders")() JOIN __table_fn("by_day")\n(1 -- ,\n, 2)'
            ),
        ),
        CraftedReferenceTestCase(
            description="references_nested_in_table_function_arguments",
            sql='SELECT * FROM __table_fn("orders_for")((SELECT id FROM __ref("customers")))',
        ),
        CraftedReferenceTestCase(
            description="hidden_in_comments_strings_and_dollar_quotes",
            sql=(
                "-- __ref(a)\nSELECT '__ref(b)', $$__table_fn(\"c\")$$, $t$ __ref(d) $t$, "
                '/* __ref(e) */ "__ref(f)", `__ref(g)` FROM __ref("h")'
            ),
        ),
        CraftedReferenceTestCase(
            description="dialect_sensitive_text",
            sql=(
                "SELECT 'it\\'s __ref(a)', E'x\\'__ref(b)', r'C:\\' AS p, '''__ref(c)''', "
                '/* x /* y */ __ref(d) */ 1 # __ref(e)\n// __ref(f)\nFROM __ref("g")'
            ),
            expected_rejected=4,
        ),
        CraftedReferenceTestCase(
            description="comments_inside_calls_are_rejected",
            sql='SELECT * FROM __ref("a" /* note */ "b") JOIN __ref(-- c\n"orders")',
            expected_rejected=2,
        ),
        CraftedReferenceTestCase(
            description="non_ascii_quoted_names_and_text",
            sql="SELECT 'é' FROM __ref(\"commandés\") JOIN __table_fn(\"größe\")('ü')",
        ),
        CraftedReferenceTestCase(
            description="wrong_reference_argument_count_is_rejected",
            sql="SELECT * FROM __ref(orders, customers)",
            expected_rejected=1,
        ),
        CraftedReferenceTestCase(
            description="unquoted_and_single_quoted_names_are_rejected",
            sql="SELECT * FROM __ref(orders) JOIN __source('raw_orders')",
            expected_rejected=2,
        ),
        CraftedReferenceTestCase(
            description="spaces_inside_calls_are_rejected",
            sql='SELECT * FROM __seed( "regions" ) JOIN __dbt_ref("shop", "orders" )',
            expected_rejected=2,
        ),
        CraftedReferenceTestCase(
            description="unclosed_text_after_a_rejected_call_fails",
            sql="SELECT * FROM __ref(orders) WHERE note = 'unclosed",
            expected_failed=1,
        ),
        CraftedReferenceTestCase(
            description="unclosed_text_before_a_rejected_call_fails",
            sql='SELECT * FROM __ref("orders" WHERE __ref(customers)',
            expected_failed=1,
        ),
        CraftedReferenceTestCase(
            description="wrong_dbt_reference_argument_count_is_rejected",
            sql="SELECT * FROM __dbt_ref(shop, orders, extra)",
            expected_rejected=1,
        ),
        CraftedReferenceTestCase(
            description="empty_table_function_call_argument",
            sql='SELECT * FROM __table_fn("orders_for")(1,,2)',
            expected_failed=1,
        ),
        CraftedReferenceTestCase(
            description="table_function_without_call_is_rejected",
            sql='SELECT * FROM __table_fn("orders_for") /* gap */ (1)',
            expected_rejected=1,
        ),
        CraftedReferenceTestCase(
            description="unquoted_table_function_name_is_rejected",
            sql="SELECT * FROM __table_fn(orders_for)(1)",
            expected_rejected=1,
        ),
        CraftedReferenceTestCase(
            description="unclosed_table_function_call",
            sql='SELECT * FROM __table_fn("orders_for")(1',
            expected_failed=1,
        ),
        CraftedReferenceTestCase(
            description="nested_reference_as_name_is_rejected",
            sql="SELECT * FROM __ref(__ref(orders))",
            expected_rejected=1,
        ),
        CraftedReferenceTestCase(
            description="non_ascii_identifier_is_rejected",
            sql="SELECT * FROM __ref(commandés)",
            expected_rejected=1,
        ),
        CraftedReferenceTestCase(
            description="unicode_whitespace_before_call_is_skipped",
            sql='SELECT * FROM __table_fn("orders_for")\u00a0(1)',
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_crafted_reference_sql_when_extracting_then_rejected_and_failed_counts_match(
    test_case: CraftedReferenceTestCase,
) -> None:
    outcome: Any = _SCANNER.extract(test_case.sql)

    assert _REJECTED_AND_FAILED[type(outcome[0])](outcome) == (
        test_case.expected_rejected,
        test_case.expected_failed,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ReferenceExtractionTestCase(
            description=name,
            sql=sql,
            expected_references=expected_references,
            expected_error=expected_error,
        )
        for name, sql, expected_references, expected_error in _REFERENCE_SQLS
    ],
    ids=lambda case: case.description,
)
def test_given_reference_sql_when_extracting_references_then_native_scanner_runs(
    test_case: ReferenceExtractionTestCase,
) -> None:
    error: str = ""
    extracted: tuple[tuple[str, str, str | None, int | None], ...] = ()
    try:
        extracted = tuple(
            (str(ref.ref_kind), ref.ref_name, ref.ref_package, ref.call_argument_count)
            for ref in extract_sql_references(sql=test_case.sql, syntax=_GENERIC_SYNTAX)
        )
    except CompileInputError as raised:
        error = str(raised)

    assert (extracted, error) == (test_case.expected_references, test_case.expected_error)


@pytest.mark.parametrize(
    "test_case",
    [
        ReferenceScanBoundTestCase(
            description="ten_thousand_references",
            sql=_MANY_CALLS,
            expected_outcome=10_000,
            expected_maximum_seconds=1.5,
        ),
        ReferenceScanBoundTestCase(
            description="one_hundred_thousand_call_arguments",
            sql=_WIDE_CALL,
            expected_outcome=1,
            expected_maximum_seconds=1.5,
        ),
        ReferenceScanBoundTestCase(
            description="thousand_nested_table_functions",
            sql=_NESTED_CALLS,
            expected_outcome=1_000,
            expected_maximum_seconds=1.5,
        ),
        ReferenceScanBoundTestCase(
            description="error_after_fifty_thousand_references",
            sql=_ERROR_AFTER_MANY,
            expected_outcome="SQL reference contains an unclosed parenthesis",
            expected_maximum_seconds=1.5,
        ),
        ReferenceScanBoundTestCase(
            description="rejected_call_after_fifty_thousand_references",
            sql=_REJECTED_AFTER_MANY,
            expected_outcome=50_001,
            expected_maximum_seconds=1.5,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_worst_case_reference_sql_when_extracting_natively_then_finishes_quickly(
    test_case: ReferenceScanBoundTestCase,
) -> None:
    started: float = time.thread_time()
    outcome: Any = _SCANNER.extract(test_case.sql)
    elapsed: float = time.thread_time() - started

    summary: int | str = _OUTCOME_SUMMARIES[type(outcome[0])](outcome)

    assert (summary, elapsed < test_case.expected_maximum_seconds) == (
        test_case.expected_outcome,
        True,
    ), elapsed


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
