"""Natively scanned `@enum`/`@const` references expand, and fail, exactly as Python's do."""

from __future__ import annotations

import random

import pytest

from tests.integration.src.sqlbuild.compiler.helpers import mismatches
from tests.integration.src.sqlbuild.compiler.model_loop._test_types import (
    DeclarationReferenceParityTestCase,
)
from tests.integration.src.sqlbuild.compiler.model_loop.helpers import (
    ReferenceParity,
    generated_failing_reference_sql,
    is_error,
    is_native,
    reference_parities,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DeclarationReferenceParityTestCase(
            description="seeded references and errors among quotes, comments and Unicode",
            seed=20261007,
            count=3000,
            expected_minimum_native_references=5000,
            expected_maximum_deferred=150,
            expected_minimum_native_errors=1200,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_sql_when_expanding_references_natively_then_python_outcome_matches(
    test_case: DeclarationReferenceParityTestCase,
) -> None:
    rng: random.Random = random.Random(test_case.seed)
    sqls: list[str] = [generated_failing_reference_sql(rng=rng) for _ in range(test_case.count)]

    parities: list[ReferenceParity] = reference_parities(sqls=sqls)

    expanded: list[ReferenceParity] = list(filter(is_native, parities))

    assert (
        mismatches(
            inputs=[parity.sql for parity in expanded],
            expected=[parity.python for parity in expanded],
            actual=[parity.native for parity in expanded],
        ),
        sum(parity.native_references for parity in expanded)
        >= test_case.expected_minimum_native_references,
        len(parities) - len(expanded) <= test_case.expected_maximum_deferred,
        sum(is_error(parity.native) for parity in expanded)
        >= test_case.expected_minimum_native_errors,
    ) == ([], True, True, True), test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
