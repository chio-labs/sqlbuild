from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.sql_analysis._helpers.scanning import (
    iter_code_positions_impl,
    skip_quoted_text_impl,
)
from tests.unit.src.sqlbuild.compiler.sql_analysis._helpers._test_types import (
    IterCodePositionsTestCase,
    SkipQuotedTextErrorTestCase,
    SkipQuotedTextSuccessTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        SkipQuotedTextSuccessTestCase(
            description="doubled quote escape",
            quoted_sql="'customer''s order'",
            expected_end=len("'customer''s order'"),
        ),
        SkipQuotedTextSuccessTestCase(
            description="backtick identifier",
            quoted_sql="`order status`",
            expected_end=len("`order status`"),
        ),
        SkipQuotedTextSuccessTestCase(
            description="doubled double quote escape",
            quoted_sql='"customer""name"',
            expected_end=len('"customer""name"'),
        ),
        SkipQuotedTextSuccessTestCase(
            description="empty quoted value",
            quoted_sql="''",
            expected_end=2,
        ),
        SkipQuotedTextSuccessTestCase(
            description="multiple adjacent escapes",
            quoted_sql="'a''''b'",
            expected_end=len("'a''''b'"),
        ),
        SkipQuotedTextSuccessTestCase(
            description="dollar quote hides apostrophes, comments and single dollars",
            quoted_sql="$$customer's order -- $5 $$",
            expected_end=len("$$customer's order -- $5 $$"),
        ),
        SkipQuotedTextSuccessTestCase(
            description="tagged dollar quote ends only at its own tag",
            quoted_sql="$order$ $$ it's $order$",
            expected_end=len("$order$ $$ it's $order$"),
        ),
        SkipQuotedTextSuccessTestCase(
            description="positional parameter dollar is one code character",
            quoted_sql="$1",
            expected_end=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_quoted_text_when_skipping_then_returns_end_position(
    test_case: SkipQuotedTextSuccessTestCase,
) -> None:
    sql: str = f"{test_case.quoted_sql} suffix"

    result: int = skip_quoted_text_impl(sql=sql, start=0)

    assert result == test_case.expected_end


@pytest.mark.parametrize(
    "test_case",
    (
        SkipQuotedTextErrorTestCase(
            description="unclosed single quote",
            sql="'customer",
            context="SQL reference",
            expected_error="SQL reference contains an unclosed quoted string",
        ),
        SkipQuotedTextErrorTestCase(
            description="unclosed dollar quote",
            sql="$order$ customer's $$",
            context="SQL reference",
            expected_error="SQL reference contains an unclosed quoted string",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_unclosed_quote_when_skipping_then_raises_contextual_error(
    test_case: SkipQuotedTextErrorTestCase,
) -> None:
    with pytest.raises(CompileInputError, match=test_case.expected_error):
        skip_quoted_text_impl(sql=test_case.sql, start=0, context=test_case.context)


@pytest.mark.parametrize(
    "test_case",
    (
        IterCodePositionsTestCase(
            description="parentheses change depth and are not yielded",
            sql="a(b)c",
            expected_positions=((0, 0), (2, 1), (4, 0)),
        ),
        IterCodePositionsTestCase(
            description="quotes and comments are skipped",
            sql="a'(b'`c`--d\n/*e*/f",
            expected_positions=((0, 0), (17, 0)),
        ),
        IterCodePositionsTestCase(
            description="dollar-quoted text is skipped",
            sql="a $$'(--$$b",
            expected_positions=((0, 0), (1, 0), (10, 0)),
        ),
        IterCodePositionsTestCase(
            description="dollars inside identifiers and parameters remain code",
            sql="a$$b $1",
            expected_positions=tuple((index, 0) for index in range(7)),
        ),
        IterCodePositionsTestCase(
            description="unbalanced close parenthesis goes below zero depth",
            sql=")a",
            expected_positions=((1, -1),),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_sql_when_iterating_code_positions_then_yields_code_offsets_with_depth(
    test_case: IterCodePositionsTestCase,
) -> None:
    assert tuple(iter_code_positions_impl(sql=test_case.sql)) == test_case.expected_positions
