"""Unexpanded direct-logic SQL tests build identical inputs under every compiler engine.

Every engine extracts tests before expansion with the native extractor, so quoted CTE names,
calls in `__macro_expected__` and malformed reference calls are rejected the same way.
"""

from __future__ import annotations

import random

import pytest

from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.frontier.types import CompilerEngine
from tests.integration.src.sqlbuild.compiler.attachments._test_types import (
    RawDirectLogicParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.attachments.helpers import (
    generated_raw_direct_logic_test,
    raw_extraction_accepts,
    raw_test_compile_outcome,
)
from tests.integration.src.sqlbuild.compiler.helpers import mismatches


@pytest.mark.parametrize(
    "test_case",
    [
        RawDirectLogicParityTestCase(
            description="quoted, non-ASCII and $ CTE names, calls in expected CTEs, bad reference calls",
            seed=20261008,
            count=3000,
            expected_minimum_extracted=400,
            expected_minimum_python_errors=600,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unexpanded_direct_logic_tests_when_compiling_in_preview_then_python_matches(
    test_case: RawDirectLogicParityTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    tests: list[tuple[str, SqlTestMode]] = [
        generated_raw_direct_logic_test(rng=rng) for _ in range(test_case.count)
    ]

    python: list[str] = [
        raw_test_compile_outcome(
            sql=sql, mode=mode, engine=CompilerEngine.PYTHON, monkeypatch=monkeypatch
        )
        for sql, mode in tests
    ]
    native: list[str] = [
        raw_test_compile_outcome(
            sql=sql, mode=mode, engine=CompilerEngine.NATIVE_PREVIEW, monkeypatch=monkeypatch
        )
        for sql, mode in tests
    ]

    assert (
        mismatches(inputs=[*tests], expected=[*python], actual=[*native]),
        sum(raw_extraction_accepts(sql=sql, mode=mode) for sql, mode in tests)
        >= test_case.expected_minimum_extracted,
        sum(item.startswith("error: ") for item in python)
        >= test_case.expected_minimum_python_errors,
    ) == ([], True, True), test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
