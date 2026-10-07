"""The native expected-model scan returns Python's names exactly or defers to Python."""

from __future__ import annotations

import random

import pytest

from tests.integration.src.sqlbuild.compiler.scopes._test_types import ExpectedNameScanTestCase
from tests.integration.src.sqlbuild.compiler.scopes.helpers import (
    LEXICAL_SYNTAXES,
    ExpectedNameScanParity,
    expected_name_scan_parity,
    generated_expected_model_sqls,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ExpectedNameScanTestCase(
            description=f"{syntax} dialect",
            syntax=syntax,
            seed=20261007 + offset,
            count=3000,
            expected_minimum_scanned=300,
            expected_minimum_deferred=300,
            expected_minimum_python_errors=300,
        )
        for offset, syntax in enumerate(LEXICAL_SYNTAXES)
    ],
    ids=lambda case: case.description,
)
def test_given_generated_sql_tests_when_scanning_expected_models_then_native_matches_or_defers(
    test_case: ExpectedNameScanTestCase,
) -> None:
    sqls: list[str] = generated_expected_model_sqls(
        rng=random.Random(test_case.seed), count=test_case.count
    )

    parity: ExpectedNameScanParity = expected_name_scan_parity(
        sqls=sqls, syntax=LEXICAL_SYNTAXES[test_case.syntax]
    )

    assert (
        parity.mismatches,
        parity.scanned >= test_case.expected_minimum_scanned,
        parity.deferred >= test_case.expected_minimum_deferred,
        parity.python_errors >= test_case.expected_minimum_python_errors,
    ) == ([], True, True, True), (parity.scanned, parity.deferred, parity.python_errors)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
