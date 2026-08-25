from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.sql_analysis._helpers.scanning import skip_quoted_text_impl
from tests.unit.src.sqlbuild.compiler.sql_analysis._helpers._test_types import (
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
    ),
    ids=lambda case: case.description,
)
def test_given_unclosed_quote_when_skipping_then_raises_contextual_error(
    test_case: SkipQuotedTextErrorTestCase,
) -> None:
    with pytest.raises(CompileInputError, match=test_case.expected_error):
        skip_quoted_text_impl(sql=test_case.sql, start=0, context=test_case.context)
