from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.sql_analysis._helpers.scanning import (
    dialect_non_code_end_impl,
    dialect_quoted_text_end_impl,
    iter_code_positions_impl,
    skip_quoted_text_impl,
)
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from tests.unit.src.sqlbuild.compiler.sql_analysis._helpers._test_types import (
    DialectNonCodeErrorTestCase,
    DialectNonCodeSuccessTestCase,
    DialectQuotedTextErrorTestCase,
    DialectQuotedTextSuccessTestCase,
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


ANSI_SYNTAX: SqlLexicalSyntax = SqlLexicalSyntax()
ESCAPE_PREFIX_SYNTAX: SqlLexicalSyntax = SqlLexicalSyntax(escape_string_prefix=True)
SINGLE_QUOTE_BACKSLASH_SYNTAX: SqlLexicalSyntax = SqlLexicalSyntax(
    backslash_escape_quotes=frozenset({"'"})
)
RAW_PREFIX_SYNTAX: SqlLexicalSyntax = SqlLexicalSyntax(
    backslash_escape_quotes=frozenset({"'", '"'}), raw_string_prefix=True
)
TRIPLE_QUOTE_SYNTAX: SqlLexicalSyntax = SqlLexicalSyntax(
    backslash_escape_quotes=frozenset({"'", '"', "`"}), triple_quoted_strings=True
)


@pytest.mark.parametrize(
    "test_case",
    (
        DialectQuotedTextSuccessTestCase(
            description="backslash escapes the quote when the dialect supports it",
            syntax=SINGLE_QUOTE_BACKSLASH_SYNTAX,
            sql="'O\\'Brien' tail",
            start=0,
            expected_end=len("'O\\'Brien'"),
        ),
        DialectQuotedTextSuccessTestCase(
            description="escaped backslash before the closing quote ends the text",
            syntax=SINGLE_QUOTE_BACKSLASH_SYNTAX,
            sql="'path\\\\' tail",
            start=0,
            expected_end=len("'path\\\\'"),
        ),
        DialectQuotedTextSuccessTestCase(
            description="doubling still escapes the quote in backslash dialects",
            syntax=SINGLE_QUOTE_BACKSLASH_SYNTAX,
            sql="'customer''s' tail",
            start=0,
            expected_end=len("'customer''s'"),
        ),
        DialectQuotedTextSuccessTestCase(
            description="backslash is literal where the dialect does not escape",
            syntax=ANSI_SYNTAX,
            sql="'O\\' tail",
            start=0,
            expected_end=len("'O\\'"),
        ),
        DialectQuotedTextSuccessTestCase(
            description="quoted identifier does not take backslash escapes from string rules",
            syntax=SINGLE_QUOTE_BACKSLASH_SYNTAX,
            sql='"note\\" tail',
            start=0,
            expected_end=len('"note\\"'),
        ),
        DialectQuotedTextSuccessTestCase(
            description="escape string prefix enables backslash escapes",
            syntax=ESCAPE_PREFIX_SYNTAX,
            sql="x = E'O\\'Brien' tail",
            start=5,
            expected_end=len("x = E'O\\'Brien'"),
        ),
        DialectQuotedTextSuccessTestCase(
            description="identifier ending in e is not an escape string prefix",
            syntax=ESCAPE_PREFIX_SYNTAX,
            sql="note'O\\' tail",
            start=4,
            expected_end=len("note'O\\'"),
        ),
        DialectQuotedTextSuccessTestCase(
            description="raw string prefix disables backslash escapes",
            syntax=RAW_PREFIX_SYNTAX,
            sql="r'C:\\' tail",
            start=1,
            expected_end=len("r'C:\\'"),
        ),
        DialectQuotedTextSuccessTestCase(
            description="triple-quoted text ends at the closing triple quote",
            syntax=TRIPLE_QUOTE_SYNTAX,
            sql="'''it's ok''' tail",
            start=0,
            expected_end=len("'''it's ok'''"),
        ),
        DialectQuotedTextSuccessTestCase(
            description="dollar-quoted text ignores quotes and backslashes",
            syntax=SINGLE_QUOTE_BACKSLASH_SYNTAX,
            sql="$$O\\'Brien$$ tail",
            start=0,
            expected_end=len("$$O\\'Brien$$"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_dialect_quoted_text_when_scanning_then_returns_end_position(
    test_case: DialectQuotedTextSuccessTestCase,
) -> None:
    result: int | None = dialect_quoted_text_end_impl(
        sql=test_case.sql, start=test_case.start, syntax=test_case.syntax
    )

    assert result == test_case.expected_end


@pytest.mark.parametrize(
    "test_case",
    (
        DialectQuotedTextErrorTestCase(
            description="escaped closing quote leaves the text unclosed",
            syntax=SINGLE_QUOTE_BACKSLASH_SYNTAX,
            sql="'O\\'",
            expected_error="unclosed quoted string",
        ),
        DialectQuotedTextErrorTestCase(
            description="unclosed triple-quoted text",
            syntax=TRIPLE_QUOTE_SYNTAX,
            sql="'''it's'",
            expected_error="unclosed quoted string",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_unclosed_dialect_quoted_text_when_scanning_then_raises(
    test_case: DialectQuotedTextErrorTestCase,
) -> None:
    with pytest.raises(CompileInputError, match=test_case.expected_error):
        dialect_quoted_text_end_impl(sql=test_case.sql, start=0, syntax=test_case.syntax)


NESTED_COMMENT_SYNTAX: SqlLexicalSyntax = SqlLexicalSyntax(nested_block_comments=True)
HASH_COMMENT_SYNTAX: SqlLexicalSyntax = SqlLexicalSyntax(
    line_comment_prefixes=frozenset({"--", "#"})
)
SLASH_COMMENT_SYNTAX: SqlLexicalSyntax = SqlLexicalSyntax(
    line_comment_prefixes=frozenset({"--", "//"})
)


@pytest.mark.parametrize(
    "test_case",
    (
        DialectNonCodeSuccessTestCase(
            description="nested block comment hides an apostrophe",
            syntax=NESTED_COMMENT_SYNTAX,
            sql="/* a /* b */ it's */ tail",
            expected_end=len("/* a /* b */ it's */"),
        ),
        DialectNonCodeSuccessTestCase(
            description="non-nesting block comment ends at the first close",
            syntax=ANSI_SYNTAX,
            sql="/* a /* b */ it's */ tail",
            expected_end=len("/* a /* b */"),
        ),
        DialectNonCodeSuccessTestCase(
            description="sibling nested comments close back to the outer comment",
            syntax=NESTED_COMMENT_SYNTAX,
            sql="/* /* a */ /* b */ c */ tail",
            expected_end=len("/* /* a */ /* b */ c */"),
        ),
        DialectNonCodeSuccessTestCase(
            description="hash line comment where the dialect supports it",
            syntax=HASH_COMMENT_SYNTAX,
            sql="# it's\ntail",
            expected_end=len("# it's\n"),
        ),
        DialectNonCodeSuccessTestCase(
            description="hash is code where the dialect has no hash comments",
            syntax=ANSI_SYNTAX,
            sql="# it's\ntail",
            expected_end=None,
        ),
        DialectNonCodeSuccessTestCase(
            description="double slash line comment where the dialect supports it",
            syntax=SLASH_COMMENT_SYNTAX,
            sql="// it's\ntail",
            expected_end=len("// it's\n"),
        ),
        DialectNonCodeSuccessTestCase(
            description="quoted text is scanned with the dialect string rules",
            syntax=SINGLE_QUOTE_BACKSLASH_SYNTAX,
            sql="'O\\'Brien' tail",
            expected_end=len("'O\\'Brien'"),
        ),
        DialectNonCodeSuccessTestCase(
            description="code character is not quoted text or a comment",
            syntax=NESTED_COMMENT_SYNTAX,
            sql="select 1",
            expected_end=None,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_dialect_sql_when_scanning_non_code_then_returns_end_position(
    test_case: DialectNonCodeSuccessTestCase,
) -> None:
    result: int | None = dialect_non_code_end_impl(
        sql=test_case.sql, start=0, syntax=test_case.syntax
    )

    assert result == test_case.expected_end


@pytest.mark.parametrize(
    "test_case",
    (
        DialectNonCodeErrorTestCase(
            description="nested block comment missing its outer close",
            syntax=NESTED_COMMENT_SYNTAX,
            sql="/* a /* b */ c",
            expected_error="unclosed block comment",
        ),
        DialectNonCodeErrorTestCase(
            description="unclosed block comment",
            syntax=ANSI_SYNTAX,
            sql="/* a",
            expected_error="unclosed block comment",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_unclosed_dialect_comment_when_scanning_then_raises(
    test_case: DialectNonCodeErrorTestCase,
) -> None:
    with pytest.raises(CompileInputError, match=test_case.expected_error):
        dialect_non_code_end_impl(sql=test_case.sql, start=0, syntax=test_case.syntax)


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
