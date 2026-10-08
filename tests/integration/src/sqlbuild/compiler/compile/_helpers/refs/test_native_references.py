"""Native reference extraction returns Python's references, rejected calls and errors exactly."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from itertools import product
from operator import itemgetter
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.compiler.compile._helpers.refs import references
from sqlbuild.compiler.compile._helpers.refs.native import extract_native_sql_references
from sqlbuild.compiler.compile._helpers.refs.references import extract_sql_references
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import ExpansionSpan, SqlReferenceOrigin, SqlReferenceScan
from sqlbuild.compiler.compile.types import SqlReferenceScanFailure
from sqlbuild.compiler.frontier.constants import COMPILER_ENGINE_ENV_VAR
from sqlbuild.compiler.frontier.types import CompilerEngine
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from tests.integration.src.sqlbuild.compiler.compile._helpers.refs._test_types import (
    CraftedReferenceParityTestCase,
    GeneratedReferenceParityTestCase,
    NativeReferenceErrorTestCase,
    ReferenceDiagnosticParityTestCase,
    ReferenceEngineTestCase,
    ReferenceScanBoundTestCase,
)
from tests.integration.src.sqlbuild.compiler.compile._helpers.refs.helpers import (
    LEXICAL_SYNTAXES,
    ReferenceParity,
    generated_reference_files,
    generated_reference_sqls,
    located_diagnostic_count,
    located_error_count,
    python_scan_not_expected,
    reference_parity,
    reported_reference_outcomes,
    source_map_at,
)
from tests.integration.src.sqlbuild.compiler.helpers import mismatches

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
    SqlReferenceScan: lambda scan: len(scan.references) + len(scan.invalid_calls),
    tuple: itemgetter(0),
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
            expected_rejected=4,
        ),
        CraftedReferenceParityTestCase(
            description="comments_inside_calls_are_rejected",
            sql='SELECT * FROM __ref("a" /* note */ "b") JOIN __ref(-- c\n"orders")',
            expected_rejected=2,
        ),
        CraftedReferenceParityTestCase(
            description="non_ascii_quoted_names_and_text",
            sql="SELECT 'é' FROM __ref(\"commandés\") JOIN __table_fn(\"größe\")('ü')",
        ),
        CraftedReferenceParityTestCase(
            description="wrong_reference_argument_count_is_rejected",
            sql="SELECT * FROM __ref(orders, customers)",
            expected_rejected=1,
        ),
        CraftedReferenceParityTestCase(
            description="unquoted_and_single_quoted_names_are_rejected",
            sql="SELECT * FROM __ref(orders) JOIN __source('raw_orders')",
            expected_rejected=2,
        ),
        CraftedReferenceParityTestCase(
            description="spaces_inside_calls_are_rejected",
            sql='SELECT * FROM __seed( "regions" ) JOIN __dbt_ref("shop", "orders" )',
            expected_rejected=2,
        ),
        CraftedReferenceParityTestCase(
            description="unclosed_text_after_a_rejected_call_fails",
            sql="SELECT * FROM __ref(orders) WHERE note = 'unclosed",
            expected_failed=1,
        ),
        CraftedReferenceParityTestCase(
            description="unclosed_text_before_a_rejected_call_fails",
            sql='SELECT * FROM __ref("orders" WHERE __ref(customers)',
            expected_failed=1,
        ),
        CraftedReferenceParityTestCase(
            description="wrong_dbt_reference_argument_count_is_rejected",
            sql="SELECT * FROM __dbt_ref(shop, orders, extra)",
            expected_rejected=1,
        ),
        CraftedReferenceParityTestCase(
            description="empty_table_function_call_argument",
            sql='SELECT * FROM __table_fn("orders_for")(1,,2)',
            expected_failed=1,
        ),
        CraftedReferenceParityTestCase(
            description="table_function_without_call_is_rejected",
            sql='SELECT * FROM __table_fn("orders_for") /* gap */ (1)',
            expected_rejected=1,
        ),
        CraftedReferenceParityTestCase(
            description="unquoted_table_function_name_is_rejected",
            sql="SELECT * FROM __table_fn(orders_for)(1)",
            expected_rejected=1,
        ),
        CraftedReferenceParityTestCase(
            description="unclosed_table_function_call",
            sql='SELECT * FROM __table_fn("orders_for")(1',
            expected_failed=1,
        ),
        CraftedReferenceParityTestCase(
            description="nested_reference_as_name_is_rejected",
            sql="SELECT * FROM __ref(__ref(orders))",
            expected_rejected=1,
        ),
        CraftedReferenceParityTestCase(
            description="non_ascii_identifier_is_rejected",
            sql="SELECT * FROM __ref(commandés)",
            expected_rejected=1,
        ),
        CraftedReferenceParityTestCase(
            description="unicode_whitespace_before_call_is_skipped",
            sql='SELECT * FROM __table_fn("orders_for")\u00a0(1)',
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_crafted_reference_sql_when_extracting_natively_then_matches_python(
    test_case: CraftedReferenceParityTestCase,
) -> None:
    parity: ReferenceParity = reference_parity(sqls=[test_case.sql], syntax=_GENERIC_SYNTAX)
    dialect_mismatches: list[list[tuple[object, object, object]]] = [
        reference_parity(sqls=[test_case.sql], syntax=syntax).mismatches
        for syntax in LEXICAL_SYNTAXES.values()
    ]

    assert (dialect_mismatches, parity.deferred, parity.rejected, parity.failed) == (
        [[]] * len(LEXICAL_SYNTAXES),
        0,
        test_case.expected_rejected,
        test_case.expected_failed,
    )


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
            expected_minimum_rejected=1400,
            expected_maximum_deferred=0,
        )
        for offset, syntax in enumerate(LEXICAL_SYNTAXES)
    ],
    ids=lambda case: case.description,
)
def test_given_generated_reference_sql_when_extracting_natively_then_matches_python(
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
            expected_native_calls=int(engine is not CompilerEngine.PYTHON),
        )
        for engine, (name, sql, expected_references, expected_error) in product(
            CompilerEngine, _ENGINE_SQLS
        )
    ],
    ids=lambda case: case.description,
)
def test_given_engine_when_extracting_references_then_only_native_engines_run_native_scanner(
    test_case: ReferenceEngineTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, test_case.engine.value)
    native_calls: list[str] = []
    native_extract: Callable[..., SqlReferenceScan | SqlReferenceScanFailure | None] = (
        references.extract_native_sql_references
    )

    def counting_extract(
        *, sql: str, syntax: SqlLexicalSyntax
    ) -> SqlReferenceScan | SqlReferenceScanFailure | None:
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
        NativeReferenceErrorTestCase(
            description="unclosed_reference_call_points_at_the_call_after_the_header",
            sql='SELECT *\nFROM __ref("orders"',
            contents='MODEL (description "Orders");\n\nSELECT *\nFROM __ref("orders"',
            source_map=source_map_at(body_start=31),
            expected_message="models/orders.sql:4:6: SQL reference contains an unclosed parenthesis",
            expected_bridge_independent=True,
        ),
        NativeReferenceErrorTestCase(
            description="empty_table_function_argument_after_a_rejected_call",
            sql='SELECT * FROM __ref(orders)\nJOIN __table_fn("orders_for")(1,,2)',
            contents='SELECT * FROM __ref(orders)\nJOIN __table_fn("orders_for")(1,,2)',
            source_map=source_map_at(body_start=0),
            expected_message="models/orders.sql:2:6: SQL reference contains an empty argument",
            expected_bridge_independent=True,
        ),
        NativeReferenceErrorTestCase(
            description="unclosed_quote_points_at_the_quote_in_code_points",
            sql="SELECT 'é', __ref(\"orders\") WHERE note = 'open",
            contents="-- é\nSELECT 'é', __ref(\"orders\") WHERE note = 'open",
            source_map=source_map_at(body_start=5),
            expected_message="models/orders.sql:2:42: SQL reference contains an unclosed quoted string",
            expected_bridge_independent=True,
        ),
        NativeReferenceErrorTestCase(
            description="fault_after_neutral_expansions_in_two_passes_maps_through_both",
            sql="SELECT 'open', 1 + 2\nFROM __ref(\"orders\"",
            contents='SELECT @enum("s").OPEN, @m()\nFROM __ref("orders"',
            source_map=source_map_at(
                body_start=0,
                passes=(
                    (ExpansionSpan(source_start=7, source_end=22, output_start=7, output_end=13),),
                    (
                        ExpansionSpan(
                            source_start=15, source_end=19, output_start=15, output_end=20
                        ),
                    ),
                ),
            ),
            expected_message="models/orders.sql:2:6: SQL reference contains an unclosed parenthesis",
            expected_bridge_independent=True,
        ),
        NativeReferenceErrorTestCase(
            description="fault_inside_macro_output_is_unlocated",
            sql='SELECT * FROM __ref("orders") /* expanded',
            contents='SELECT * FROM __ref("orders") @expand()',
            source_map=source_map_at(
                body_start=0,
                passes=(
                    (
                        ExpansionSpan(
                            source_start=30, source_end=39, output_start=30, output_end=41
                        ),
                    ),
                ),
            ),
            expected_message="models/orders.sql: SQL reference contains an unclosed block comment",
            expected_bridge_independent=False,
        ),
        NativeReferenceErrorTestCase(
            description="authored_fault_shaped_by_an_unclosed_macro_quote_is_unlocated",
            sql="SELECT 'x || ' || note || 'open",
            contents="SELECT @q() || ' || note || 'open",
            source_map=source_map_at(
                body_start=0,
                passes=(
                    (ExpansionSpan(source_start=7, source_end=11, output_start=7, output_end=9),),
                ),
            ),
            expected_message="models/orders.sql: SQL reference contains an unclosed quoted string",
            expected_bridge_independent=False,
        ),
        NativeReferenceErrorTestCase(
            description="without_a_source_map_the_file_alone_is_named",
            sql='SELECT *\nFROM __ref("orders"',
            contents='SELECT *\nFROM __ref("orders"',
            source_map=None,
            expected_message="models/orders.sql: SQL reference contains an unclosed parenthesis",
            expected_bridge_independent=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_native_reference_error_when_extracting_then_raised_located_without_python_rescan(
    test_case: NativeReferenceErrorTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(COMPILER_ENGINE_ENV_VAR, CompilerEngine.NATIVE_PREVIEW.value)
    monkeypatch.setattr(references, "python_reference_scan", python_scan_not_expected)

    with pytest.raises(CompileInputError) as raised:
        _ = extract_sql_references(
            sql=test_case.sql,
            syntax=_GENERIC_SYNTAX,
            origin=SqlReferenceOrigin(
                file_path=Path("/project/models/orders.sql"),
                relative_path=Path("models/orders.sql"),
                contents=test_case.contents,
                source_map=test_case.source_map,
            ),
        )

    assert (
        type(raised.value),
        str(raised.value),
        raised.value.code,
        raised.value.help,
        raised.value.bridge_independent,
    ) == (
        CompileInputError,
        test_case.expected_message,
        "P001",
        None,
        test_case.expected_bridge_independent,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ReferenceDiagnosticParityTestCase(
            description=f"{syntax}_syntax",
            syntax=syntax,
            seed=20261009 + offset,
            count=400,
            expected_minimum_located=120,
            expected_minimum_located_errors=90,
        )
        for offset, syntax in enumerate(LEXICAL_SYNTAXES)
    ],
    ids=lambda case: case.description,
)
def test_given_generated_files_when_reporting_rejected_calls_then_engines_report_identically(
    test_case: ReferenceDiagnosticParityTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    files: list[tuple[str, str]] = generated_reference_files(
        rng=random.Random(test_case.seed), count=test_case.count
    )
    syntax: SqlLexicalSyntax = LEXICAL_SYNTAXES[test_case.syntax]

    python: list[object] = reported_reference_outcomes(
        files=files, syntax=syntax, engine=CompilerEngine.PYTHON, monkeypatch=monkeypatch
    )
    preview: list[object] = reported_reference_outcomes(
        files=files, syntax=syntax, engine=CompilerEngine.NATIVE_PREVIEW, monkeypatch=monkeypatch
    )

    assert (
        mismatches(inputs=[body for _, body in files], expected=python, actual=preview),
        located_diagnostic_count(outcomes=python) >= test_case.expected_minimum_located,
        located_error_count(outcomes=python) >= test_case.expected_minimum_located_errors,
    ) == ([], True, True)


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
            expected_outcome=50_001,
            expected_maximum_seconds=0.5,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_worst_case_reference_sql_when_extracting_natively_then_finishes_quickly(
    test_case: ReferenceScanBoundTestCase,
) -> None:
    started: float = time.thread_time()
    outcome: SqlReferenceScan | SqlReferenceScanFailure | None = extract_native_sql_references(
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
