"""The native cursor intrinsic check accepts and rejects SQL exactly as Python does."""

from __future__ import annotations

import random
from itertools import compress

import pytest

from tests.integration.src.sqlbuild.compiler.attachments._test_types import (
    CursorIntrinsicParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.attachments.helpers import (
    generated_intrinsic_sql,
    native_intrinsic_outcome,
    python_intrinsic_outcome,
)
from tests.integration.src.sqlbuild.compiler.helpers import mismatches


@pytest.mark.parametrize(
    "test_case",
    [
        CursorIntrinsicParityTestCase(
            description="seeded intrinsic names, quotes, comments and identifier neighbours",
            seed=20261008,
            count=20000,
            expected_minimum_free=10000,
            expected_minimum_native_errors=6000,
            expected_minimum_python_errors=8000,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_sql_when_checking_natively_then_python_outcome_matches(
    test_case: CursorIntrinsicParityTestCase,
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    sqls: list[str] = [generated_intrinsic_sql(rng=rng) for _ in range(test_case.count)]

    native: list[tuple[bool, str | None]] = list(map(native_intrinsic_outcome, sqls))
    answered: list[int] = list(compress(range(len(sqls)), [outcome[0] for outcome in native]))
    python: list[str | None] = list(map(python_intrinsic_outcome, sqls))

    assert (
        mismatches(
            inputs=[sqls[index] for index in answered],
            expected=[python[index] for index in answered],
            actual=[native[index][1] for index in answered],
        ),
        sum(native[index][1] is None for index in answered) >= test_case.expected_minimum_free,
        sum(native[index][1] is not None for index in answered)
        >= test_case.expected_minimum_native_errors,
        len(python) - python.count(None) >= test_case.expected_minimum_python_errors,
    ) == ([], True, True, True), test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
