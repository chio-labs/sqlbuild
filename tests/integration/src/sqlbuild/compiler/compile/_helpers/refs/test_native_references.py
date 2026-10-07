"""Native reference extraction returns Python's references or error exactly, or defers to Python."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from itertools import product
from typing import Any

import pytest

from sqlbuild.compiler.compile._helpers.refs import references
from sqlbuild.compiler.compile._helpers.refs.native import extract_native_sql_references
from sqlbuild.compiler.compile._helpers.refs.references import extract_sql_references
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileSqlReference
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.compiler.frontier.exceptions import NativeStageMismatchError
from sqlbuild.compiler.frontier.types import CompilerEngine
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from tests.integration.src.sqlbuild.compiler.compile._helpers.refs._test_types import (
    CraftedReferenceParityTestCase,
    GeneratedReferenceParityTestCase,
    ReferenceEngineTestCase,
    ReferenceMismatchTestCase,
    ReferenceScanBoundTestCase,
)
from tests.integration.src.sqlbuild.compiler.compile._helpers.refs.helpers import (
    LEXICAL_SYNTAXES,
    ReferenceParity,
    generated_reference_sqls,
    reference_parity,
)

_GENERIC_SYNTAX: SqlLexicalSyntax = LEXICAL_SYNTAXES["generic"]
_ENGINE_SQLS: tuple[
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
_OUTCOME_SUMMARIES: dict[type, Callable[[Any], int | str]] = {
    tuple: len,
    str: str,
    type(None): repr,
}
_MANY_REFERENCES: str = "SELECT 1 FROM " + " JOIN ".join(
    f'__ref("orders_{index}")' for index in range(50_000)
)
_ERROR_AFTER_MANY: str = _MANY_REFERENCES + ' JOIN __ref("orders"'
_REJECTED_AFTER_MANY: str = _MANY_REFERENCES + " JOIN __ref(orders, customers)"


@pytest.mark.parametrize(
    "test_case",
    [
        CraftedReferenceParityTestCase(
            description="every_kind_in_authored_order",
            sql=(
                'SELECT * FROM __ref("orders") JOIN __source("raw_orders") '
                'JOIN __seed("regions") JOIN __dbt_ref("shop" ,\x1c"customers") '
                'WHERE __udf("clean")(x) > 0 OR __dbt_ref("orders") IS NULL'
            ),
        ),
        CraftedReferenceParityTestCase(
            description="table_function_argument_counts",
            sql=(
                "SELECT * FROM __table_fn(\"expand_orders\") ( 1, f(2, 3), 'a,b' /* , */ ) "
                'JOIN __table_fn("daily_orders")() JOIN __table_fn("by_day")\n(1 -- ,\n, 2)'
            ),
        ),
        CraftedReferenceParityTestCase(
            description="references_nested_in_table_function_arguments",
            sql='SELECT * FROM __table_fn("orders_for")((SELECT id FROM __ref("customers")))',
        ),
        CraftedReferenceParityTestCase(
            description="hidden_in_comments_strings_and_dollar_quotes",
            sql=(
                "-- __ref(a)\nSELECT '__ref(b)', $$__table_fn(\"c\")$$, $t$ __ref(d) $t$, "
                '/* __ref(e) */ "__ref(f)", `__ref(g)` FROM __ref("h")'
            ),
        ),
        CraftedReferenceParityTestCase(
            description="dialect_sensitive_text",
            sql=(
                "SELECT 'it\\'s __ref(a)', E'x\\'__ref(b)', r'C:\\' AS p, '''__ref(c)''', "
                '/* x /* y */ __ref(d) */ 1 # __ref(e)\n// __ref(f)\nFROM __ref("g")'
            ),
            expected_deferred=True,
        ),
        CraftedReferenceParityTestCase(
            description="comments_inside_calls_are_rejected",
            sql='SELECT * FROM __ref("a" /* note */ "b") JOIN __ref(-- c\n"orders")',
            expected_deferred=True,
        ),
        CraftedReferenceParityTestCase(
            description="non_ascii_quoted_names_and_text",
            sql="SELECT 'é' FROM __ref(\"commandés\") JOIN __table_fn(\"größe\")('ü')",
        ),
        CraftedReferenceParityTestCase(
            description="wrong_reference_argument_count_is_rejected",
            sql="SELECT * FROM __ref(orders, customers)",
            expected_deferred=True,
        ),
        CraftedReferenceParityTestCase(
            description="unquoted_and_single_quoted_names_are_rejected",
            sql="SELECT * FROM __ref(orders) JOIN __source('raw_orders')",
            expected_deferred=True,
        ),
        CraftedReferenceParityTestCase(
            description="spaces_inside_calls_are_rejected",
            sql='SELECT * FROM __seed( "regions" ) JOIN __dbt_ref("shop", "orders" )',
            expected_deferred=True,
        ),
        CraftedReferenceParityTestCase(
            description="unclosed_text_after_a_rejected_call_is_rejected",
            sql="SELECT * FROM __ref(orders) WHERE note = 'unclosed",
            expected_deferred=True,
        ),
        CraftedReferenceParityTestCase(
            description="unclosed_text_before_a_rejected_call_fails",
            sql='SELECT * FROM __ref("orders" WHERE __ref(customers)',
        ),
        CraftedReferenceParityTestCase(
            description="wrong_dbt_reference_argument_count_is_rejected",
            sql="SELECT * FROM __dbt_ref(shop, orders, extra)",
            expected_deferred=True,
        ),
        CraftedReferenceParityTestCase(
            description="empty_table_function_call_argument",
            sql='SELECT * FROM __table_fn("orders_for")(1,,2)',
        ),
        CraftedReferenceParityTestCase(
            description="table_function_without_call_is_rejected",
            sql='SELECT * FROM __table_fn("orders_for") /* gap */ (1)',
            expected_deferred=True,
        ),
        CraftedReferenceParityTestCase(
            description="unquoted_table_function_name_is_rejected",
            sql="SELECT * FROM __table_fn(orders_for)(1)",
            expected_deferred=True,
        ),
        CraftedReferenceParityTestCase(
            description="unclosed_table_function_call",
            sql='SELECT * FROM __table_fn("orders_for")(1',
        ),
        CraftedReferenceParityTestCase(
            description="nested_reference_as_name_is_rejected",
            sql="SELECT * FROM __ref(__ref(orders))",
            expected_deferred=True,
        ),
        CraftedReferenceParityTestCase(
            description="non_ascii_identifier_defers",
            sql="SELECT * FROM __ref(commandés)",
            expected_deferred=True,
        ),
        CraftedReferenceParityTestCase(
            description="unicode_whitespace_before_call_defers",
            sql='SELECT * FROM __table_fn("orders_for")\u00a0(1)',
            expected_deferred=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_crafted_reference_sql_when_extracting_natively_then_matches_python_or_defers(
    test_case: CraftedReferenceParityTestCase,
) -> None:
    parity: ReferenceParity = reference_parity(sqls=[test_case.sql], syntax=_GENERIC_SYNTAX)
    dialect_mismatches: list[list[tuple[object, object, object]]] = [
        reference_parity(sqls=[test_case.sql], syntax=syntax).mismatches
        for syntax in LEXICAL_SYNTAXES.values()
    ]

    assert dialect_mismatches == [[]] * len(LEXICAL_SYNTAXES)
    assert parity.deferred + parity.rejected == int(test_case.expected_deferred)


@pytest.mark.parametrize(
    "test_case",
    [
        GeneratedReferenceParityTestCase(
            description=f"{syntax}_syntax",
            syntax=syntax,
            seed=20261007 + offset,
            count=3000,
            expected_minimum_extracted=700,
            expected_minimum_failed=500,
            expected_minimum_table_functions=300,
            expected_minimum_rejected=1000,
            expected_maximum_deferred=400,
        )
        for offset, syntax in enumerate(LEXICAL_SYNTAXES)
    ],
    ids=lambda case: case.description,
)
def test_given_generated_reference_sql_when_extracting_natively_then_matches_python_or_defers(
    test_case: GeneratedReferenceParityTestCase,
) -> None:
    sqls: list[str] = generated_reference_sqls(
        rng=random.Random(test_case.seed), count=test_case.count
    )

    parity: ReferenceParity = reference_parity(sqls=sqls, syntax=LEXICAL_SYNTAXES[test_case.syntax])

    assert (
        parity.mismatches,
        parity.extracted >= test_case.expected_minimum_extracted,
        parity.failed >= test_case.expected_minimum_failed,
        parity.table_functions >= test_case.expected_minimum_table_functions,
        parity.rejected >= test_case.expected_minimum_rejected,
        parity.deferred <= test_case.expected_maximum_deferred,
    ) == ([], True, True, True, True, True), parity


@pytest.mark.parametrize(
    "test_case",
    [
        ReferenceEngineTestCase(
            description=f"{engine}_{name}",
            engine=engine,
            sql=sql,
            expected_references=expected_references,
            expected_error=expected_error,
            expected_native_calls=int(engine is CompilerEngine.NATIVE_PREVIEW),
        )
        for engine, (name, sql, expected_references, expected_error) in product(
            CompilerEngine, _ENGINE_SQLS
        )
    ],
    ids=lambda case: case.description,
)
def test_given_engine_when_extracting_references_then_only_preview_runs_native_scanner(
    test_case: ReferenceEngineTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, test_case.engine.value)
    native_calls: list[str] = []
    native_extract: Callable[..., tuple[CompileSqlReference, ...] | str | None] = (
        references.extract_native_sql_references
    )

    def counting_extract(
        *, sql: str, syntax: SqlLexicalSyntax
    ) -> tuple[CompileSqlReference, ...] | str | None:
        native_calls.append(sql)
        return native_extract(sql=sql, syntax=syntax)

    monkeypatch.setattr(references, "extract_native_sql_references", counting_extract)

    error: str = ""
    extracted: tuple[tuple[str, str, str | None, int | None], ...] = ()
    try:
        extracted = tuple(
            (str(ref.ref_kind), ref.ref_name, ref.ref_package, ref.call_argument_count)
            for ref in extract_sql_references(sql=test_case.sql, syntax=_GENERIC_SYNTAX)
        )
    except CompileInputError as raised:
        error = str(raised)

    assert (extracted, error, len(native_calls)) == (
        test_case.expected_references,
        test_case.expected_error,
        test_case.expected_native_calls,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ReferenceMismatchTestCase(
            description="python_extracts_references",
            sql='SELECT * FROM __ref("orders")',
            native_message="SQL reference contains an empty argument",
            expected_python_outcome="found 1 reference(s) and 0 rejected call(s)",
        ),
        ReferenceMismatchTestCase(
            description="python_rejects_a_call",
            sql="SELECT * FROM __ref(orders)",
            native_message="SQL reference contains an empty argument",
            expected_python_outcome="found 0 reference(s) and 1 rejected call(s)",
        ),
        ReferenceMismatchTestCase(
            description="python_raises_a_different_error",
            sql='SELECT * FROM __ref("orders"',
            native_message="SQL reference contains an empty argument",
            expected_python_outcome="raised 'SQL reference contains an unclosed parenthesis'",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_native_error_python_disagrees_with_when_extracting_then_raises_mismatch(
    test_case: ReferenceMismatchTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, CompilerEngine.NATIVE_PREVIEW.value)

    def failing_extract(*, sql: str, syntax: SqlLexicalSyntax) -> str:
        del sql, syntax
        return test_case.native_message

    monkeypatch.setattr(references, "extract_native_sql_references", failing_extract)

    with pytest.raises(NativeStageMismatchError) as raised:
        _ = extract_sql_references(sql=test_case.sql, syntax=_GENERIC_SYNTAX)

    assert test_case.expected_python_outcome in str(raised.value)
    assert repr(test_case.native_message) in str(raised.value)


@pytest.mark.parametrize(
    "test_case",
    [
        ReferenceScanBoundTestCase(
            description="ten_thousand_references",
            sql=_MANY_CALLS,
            expected_outcome=10_000,
            expected_maximum_seconds=0.5,
        ),
        ReferenceScanBoundTestCase(
            description="one_hundred_thousand_call_arguments",
            sql=_WIDE_CALL,
            expected_outcome=1,
            expected_maximum_seconds=0.5,
        ),
        ReferenceScanBoundTestCase(
            description="thousand_nested_table_functions",
            sql=_NESTED_CALLS,
            expected_outcome=1_000,
            expected_maximum_seconds=0.5,
        ),
        ReferenceScanBoundTestCase(
            description="error_after_fifty_thousand_references",
            sql=_ERROR_AFTER_MANY,
            expected_outcome="SQL reference contains an unclosed parenthesis",
            expected_maximum_seconds=0.5,
        ),
        ReferenceScanBoundTestCase(
            description="rejected_call_after_fifty_thousand_references",
            sql=_REJECTED_AFTER_MANY,
            expected_outcome="None",
            expected_maximum_seconds=0.5,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_worst_case_reference_sql_when_extracting_natively_then_finishes_quickly(
    test_case: ReferenceScanBoundTestCase,
) -> None:
    started: float = time.thread_time()
    outcome: tuple[CompileSqlReference, ...] | str | None = extract_native_sql_references(
        sql=test_case.sql, syntax=_GENERIC_SYNTAX
    )
    elapsed: float = time.thread_time() - started

    summary: int | str = _OUTCOME_SUMMARIES[type(outcome)](outcome)

    assert (summary, elapsed < test_case.expected_maximum_seconds) == (
        test_case.expected_outcome,
        True,
    ), elapsed


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
