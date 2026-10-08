"""Test and scenario bodies gain an omitted `SELECT 1` identically under the preview engine."""

from __future__ import annotations

import random

import pytest

from sqlbuild.compiler.frontier.types import CompilerEngine
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from tests.integration.src.sqlbuild.compiler.attachments._test_types import (
    OmittedSelectParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.attachments.helpers import (
    completed_body,
    generated_test_body,
)
from tests.integration.src.sqlbuild.compiler.helpers import mismatches


@pytest.mark.parametrize(
    "test_case",
    [
        OmittedSelectParityTestCase(
            description="generic syntax",
            seed=20261008,
            count=4000,
            syntax=SqlLexicalSyntax(),
            expected_minimum_completed=1000,
        ),
        OmittedSelectParityTestCase(
            description="backslash escapes, raw and triple-quoted strings, hash comments",
            seed=20261009,
            count=4000,
            syntax=SqlLexicalSyntax(
                backslash_escape_quotes=frozenset({"'", '"'}),
                raw_string_prefix=True,
                triple_quoted_strings=True,
                line_comment_prefixes=frozenset({"--", "#"}),
            ),
            expected_minimum_completed=1000,
        ),
        OmittedSelectParityTestCase(
            description="escape strings and nested block comments",
            seed=20261010,
            count=4000,
            syntax=SqlLexicalSyntax(escape_string_prefix=True, nested_block_comments=True),
            expected_minimum_completed=1000,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_bodies_when_completing_select_then_python_output_matches(
    test_case: OmittedSelectParityTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    sqls: list[str] = [generated_test_body(rng=rng) for _ in range(test_case.count)]

    python: list[str] = [
        completed_body(
            sql=sql, syntax=test_case.syntax, engine=CompilerEngine.PYTHON, monkeypatch=monkeypatch
        )
        for sql in sqls
    ]
    preview: list[str] = [
        completed_body(
            sql=sql,
            syntax=test_case.syntax,
            engine=CompilerEngine.NATIVE_PREVIEW,
            monkeypatch=monkeypatch,
        )
        for sql in sqls
    ]

    assert (
        mismatches(inputs=[*sqls], expected=[*python], actual=[*preview]),
        sum(map(str.__ne__, python, sqls)) >= test_case.expected_minimum_completed,
    ) == ([], True), test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
