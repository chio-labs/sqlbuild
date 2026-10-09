"""SQL test `@param` references expand identically under the preview engine."""

from __future__ import annotations

import random

import pytest

from sqlbuild.compiler.frontier.types import CompilerEngine
from tests.integration.src.sqlbuild.compiler.attachments._test_types import (
    ParameterParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.attachments.helpers import (
    generated_parameter_sql,
    parameter_outcome,
)
from tests.integration.src.sqlbuild.compiler.helpers import mismatches


@pytest.mark.parametrize(
    "test_case",
    [
        ParameterParityTestCase(
            description="seeded references, malformed and undeclared names, quotes, comments",
            seed=20261008,
            count=3000,
            expected_minimum_expanded=800,
            expected_minimum_python_errors=800,
            expected_minimum_exact_errors=1500,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_test_bodies_when_expanding_parameters_then_python_output_matches(
    test_case: ParameterParityTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    sqls: list[str] = [generated_parameter_sql(rng=rng) for _ in range(test_case.count)]

    python: list[object] = [
        parameter_outcome(sql=sql, engine=CompilerEngine.PYTHON, monkeypatch=monkeypatch)
        for sql in sqls
    ]
    preview: list[object] = [
        parameter_outcome(sql=sql, engine=CompilerEngine.NATIVE_PREVIEW, monkeypatch=monkeypatch)
        for sql in sqls
    ]

    assert (
        mismatches(inputs=[*sqls], expected=python, actual=preview),
        sum(isinstance(item, tuple) for item in python) >= test_case.expected_minimum_expanded,
        sum(isinstance(item, str) for item in python) >= test_case.expected_minimum_python_errors,
        sum(isinstance(item, str) for item in preview) >= test_case.expected_minimum_exact_errors,
    ) == ([], True, True, True), test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
