"""The native cursor intrinsic check accepts only SQL that Python accepts."""

from __future__ import annotations

import random

import pytest

from tests.integration.src.sqlbuild.compiler.attachments._test_types import (
    CursorIntrinsicParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.attachments.helpers import (
    generated_intrinsic_sql,
    native_intrinsic_free,
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
            expected_minimum_python_errors=8000,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_sql_when_checking_natively_then_only_python_accepted_sql_is_free(
    test_case: CursorIntrinsicParityTestCase,
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    sqls: list[str] = [generated_intrinsic_sql(rng=rng) for _ in range(test_case.count)]

    free: list[str] = list(filter(native_intrinsic_free, sqls))
    python: list[str | None] = list(map(python_intrinsic_outcome, sqls))

    assert (
        mismatches(
            inputs=[*free],
            expected=[None] * len(free),
            actual=[*map(python_intrinsic_outcome, free)],
        ),
        len(free) >= test_case.expected_minimum_free,
        len(python) - python.count(None) >= test_case.expected_minimum_python_errors,
    ) == ([], True, True), test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
