"""The native relationship scans return Python's names, CTEs and errors exactly."""

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
            expected_minimum_python_errors=300,
            expected_minimum_native_errors=3000,
        )
        for offset, syntax in enumerate(LEXICAL_SYNTAXES)
    ],
    ids=lambda case: case.description,
)
def test_given_generated_sql_when_scanning_relationships_then_native_matches_python(
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
        parity.python_errors >= test_case.expected_minimum_python_errors,
        parity.native_errors >= test_case.expected_minimum_native_errors,
    ) == ([], True, True, True), (
        parity.scanned,
        parity.python_errors,
        parity.native_errors,
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
