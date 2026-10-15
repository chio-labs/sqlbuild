from __future__ import annotations

import pytest

import sqlbuild._native as _native
from sqlbuild._native import CompileInputError, SqlLexicalSyntax
from tests.unit.src.sqlbuild.compiler.sql_analysis._helpers._test_types import (
    DialectMatchingParenTestCase,
    DialectNonCodeErrorTestCase,
    DialectNonCodeSuccessTestCase,
    DialectQuotedTextErrorTestCase,
    DialectQuotedTextSuccessTestCase,
    RequiresDialectScanTestCase,
    SkipQuotedTextErrorTestCase,
    SkipQuotedTextSuccessTestCase,
)
from tests.unit.src.sqlbuild.compiler.sql_analysis._helpers.helpers import (
    dialect_scanner,
    generic_scanner,
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

    result: int | None = generic_scanner(sql=sql).non_code_end(0)

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
        generic_scanner(sql=test_case.sql, context=test_case.context).non_code_end(0)


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
    result: int | None = dialect_scanner(sql=test_case.sql, syntax=test_case.syntax).non_code_end(
        test_case.start
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
        dialect_scanner(sql=test_case.sql, syntax=test_case.syntax).non_code_end(0)


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
    result: int | None = dialect_scanner(sql=test_case.sql, syntax=test_case.syntax).non_code_end(0)

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
        dialect_scanner(sql=test_case.sql, syntax=test_case.syntax).non_code_end(0)


@pytest.mark.parametrize(
    "test_case",
    (
        RequiresDialectScanTestCase(
            description="backslash under backslash escapes",
            syntax=SINGLE_QUOTE_BACKSLASH_SYNTAX,
            sql="SELECT 'O\\'Brien'",
            expected_reads_differently=True,
        ),
        RequiresDialectScanTestCase(
            description="backslash under escape-string prefixes",
            syntax=ESCAPE_PREFIX_SYNTAX,
            sql="SELECT E'O\\'Brien'",
            expected_reads_differently=True,
        ),
        RequiresDialectScanTestCase(
            description="backslash under generic sql",
            syntax=ANSI_SYNTAX,
            sql="SELECT 'C:\\'",
            expected_reads_differently=False,
        ),
        RequiresDialectScanTestCase(
            description="triple quotes",
            syntax=TRIPLE_QUOTE_SYNTAX,
            sql='SELECT """note"""',
            expected_reads_differently=True,
        ),
        RequiresDialectScanTestCase(
            description="second block comment opener under nested comments",
            syntax=NESTED_COMMENT_SYNTAX,
            sql="/* a /* b */ */ SELECT 1",
            expected_reads_differently=True,
        ),
        RequiresDialectScanTestCase(
            description="single block comment under nested comments",
            syntax=NESTED_COMMENT_SYNTAX,
            sql="/* a */ SELECT 1",
            expected_reads_differently=False,
        ),
        RequiresDialectScanTestCase(
            description="dialect line comment prefix",
            syntax=HASH_COMMENT_SYNTAX,
            sql="SELECT 1 # note",
            expected_reads_differently=True,
        ),
        RequiresDialectScanTestCase(
            description="plain sql under a dialect",
            syntax=SINGLE_QUOTE_BACKSLASH_SYNTAX,
            sql="SELECT 'customer''s order' -- note",
            expected_reads_differently=False,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_sql_when_checking_dialect_sensitivity_then_reports_differences(
    test_case: RequiresDialectScanTestCase,
) -> None:
    reads_differently: bool = test_case.syntax.reads_differently_from_generic(test_case.sql)

    assert reads_differently is test_case.expected_reads_differently


@pytest.mark.parametrize(
    "test_case",
    (
        DialectMatchingParenTestCase(
            description="backslash-escaped quote hides a parenthesis",
            native_syntax=SINGLE_QUOTE_BACKSLASH_SYNTAX.native_mapping,
            sql="('O\\') ' AS name) tail",
            expected_index=len("('O\\') ' AS name"),
        ),
        DialectMatchingParenTestCase(
            description="hash comment hides a parenthesis",
            native_syntax=HASH_COMMENT_SYNTAX.native_mapping,
            sql="(1 # )\n) tail",
            expected_index=len("(1 # )\n"),
        ),
        DialectMatchingParenTestCase(
            description="generic scanning keeps the backslash literal",
            native_syntax=None,
            sql="('C:\\') tail",
            expected_index=len("('C:\\'"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_dialect_sql_when_matching_parenthesis_then_follows_dialect_rules(
    test_case: DialectMatchingParenTestCase,
) -> None:
    assert (
        _native.SqlCodeScanner(test_case.sql, test_case.native_syntax, "SQL").matching_paren(0)
        == test_case.expected_index
    )
