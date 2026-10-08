"""Unexpanded direct-logic SQL tests extract identically under the preview engine."""

from __future__ import annotations

import random

import pytest

from sqlbuild.compiler.compile.models import CompileSqlTestCtes
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.frontier.types import CompilerEngine
from tests.integration.src.sqlbuild.compiler.attachments._test_types import (
    RawDirectLogicParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.attachments.helpers import (
    generated_direct_logic_test,
    raw_extraction_outcome,
)
from tests.integration.src.sqlbuild.compiler.helpers import mismatches


@pytest.mark.parametrize(
    "test_case",
    [
        RawDirectLogicParityTestCase(
            description="macro, UDF and table-function tests before macro and variable expansion",
            seed=20261008,
            count=3000,
            expected_minimum_extracted=600,
            expected_minimum_python_errors=600,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unexpanded_direct_logic_tests_when_extracting_natively_then_python_matches(
    test_case: RawDirectLogicParityTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    tests: list[tuple[str, SqlTestMode]] = [
        generated_direct_logic_test(rng=rng) for _ in range(test_case.count)
    ]

    python: list[object] = [
        raw_extraction_outcome(
            sql=sql, mode=mode, engine=CompilerEngine.PYTHON, monkeypatch=monkeypatch
        )
        for sql, mode in tests
    ]
    native: list[object] = [
        raw_extraction_outcome(
            sql=sql, mode=mode, engine=CompilerEngine.NATIVE_PREVIEW, monkeypatch=monkeypatch
        )
        for sql, mode in tests
    ]

    assert (
        mismatches(inputs=[*tests], expected=python, actual=native),
        sum(isinstance(item, CompileSqlTestCtes) for item in python)
        >= test_case.expected_minimum_extracted,
        sum(isinstance(item, str) for item in python) >= test_case.expected_minimum_python_errors,
    ) == ([], True, True), test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
