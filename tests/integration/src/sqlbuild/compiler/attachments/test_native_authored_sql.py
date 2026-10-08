"""Authored SQL outside models expands identically under the preview engine."""

from __future__ import annotations

import random

import pytest

from sqlbuild.compiler.compile.models import AuthoredSqlExpansionResult
from sqlbuild.compiler.frontier.types import CompilerEngine
from tests.integration.src.sqlbuild.compiler.attachments._test_types import (
    AuthoredSqlParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.attachments.helpers import (
    authored_outcome,
    generated_authored_sql,
    generated_dollar_authored_sql,
)
from tests.integration.src.sqlbuild.compiler.helpers import mismatches


@pytest.mark.parametrize(
    "test_case",
    [
        AuthoredSqlParityTestCase(
            description="seeded variables, enum and constant references, quotes and comments",
            seed=20261008,
            count=2000,
            generate=lambda rng: generated_authored_sql(rng=rng),
            expected_minimum_expanded=600,
            expected_minimum_python_errors=300,
        ),
        AuthoredSqlParityTestCase(
            description="dollar quotes around variables, enum and constant references",
            seed=550,
            count=2000,
            generate=lambda rng: generated_dollar_authored_sql(rng=rng),
            expected_minimum_expanded=300,
            expected_minimum_python_errors=300,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_authored_sql_when_expanding_with_preview_then_python_output_matches(
    test_case: AuthoredSqlParityTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    sqls: list[str] = [test_case.generate(rng) for _ in range(test_case.count)]

    python: list[AuthoredSqlExpansionResult | str] = [
        authored_outcome(sql=sql, engine=CompilerEngine.PYTHON, monkeypatch=monkeypatch)
        for sql in sqls
    ]
    preview: list[AuthoredSqlExpansionResult | str] = [
        authored_outcome(sql=sql, engine=CompilerEngine.NATIVE_PREVIEW, monkeypatch=monkeypatch)
        for sql in sqls
    ]

    assert (
        mismatches(inputs=[*sqls], expected=[*python], actual=[*preview]),
        sum(isinstance(item, AuthoredSqlExpansionResult) for item in python)
        >= test_case.expected_minimum_expanded,
        sum(isinstance(item, str) for item in python) >= test_case.expected_minimum_python_errors,
    ) == ([], True, True), test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
