"""The native relationship scans return Python's recorded names, CTEs and errors exactly."""

from __future__ import annotations

import random

import pytest

from tests.integration.src.sqlbuild.compiler.helpers import (
    golden_differences,
    golden_name,
    read_golden,
)
from tests.integration.src.sqlbuild.compiler.scopes._test_types import (
    ExpectedNameScanTestCase,
    RelationshipEdgeTestCase,
)
from tests.integration.src.sqlbuild.compiler.scopes.helpers import (
    LEXICAL_SYNTAXES,
    UNICODE_RELATIONSHIP_CHARACTERS,
    RelationshipScans,
    generated_expected_model_sqls,
    relationship_scans,
    unicode_relationship_sqls,
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
            expected_minimum_errors=3000,
        )
        for offset, syntax in enumerate(LEXICAL_SYNTAXES)
    ],
    ids=lambda case: case.description,
)
def test_given_generated_sql_when_scanning_relationships_then_native_matches_python_golden(
    test_case: ExpectedNameScanTestCase,
) -> None:
    sqls: list[str] = generated_expected_model_sqls(
        rng=random.Random(test_case.seed), count=test_case.count
    )

    scans: RelationshipScans = relationship_scans(
        sqls=sqls, syntax=LEXICAL_SYNTAXES[test_case.syntax]
    )

    assert (
        golden_differences(
            read_golden(golden_name("relationship_scan", test_case.description)), scans.golden
        ),
        scans.scanned >= test_case.expected_minimum_scanned,
        scans.errors >= test_case.expected_minimum_errors,
    ) == ([], True, True), (scans.scanned, scans.errors)


@pytest.mark.parametrize(
    "test_case",
    [
        RelationshipEdgeTestCase(
            description="unicode identifier and keyword edges",
            characters=UNICODE_RELATIONSHIP_CHARACTERS,
            expected_minimum_scanned=100,
            expected_minimum_errors=100,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unicode_edges_when_scanning_relationships_then_native_matches_python_golden(
    test_case: RelationshipEdgeTestCase,
) -> None:
    scans: RelationshipScans = relationship_scans(
        sqls=unicode_relationship_sqls(test_case.characters), syntax=LEXICAL_SYNTAXES["generic"]
    )

    assert (
        golden_differences(
            read_golden(golden_name("relationship_scan", test_case.description)), scans.golden
        ),
        scans.scanned >= test_case.expected_minimum_scanned,
        scans.errors >= test_case.expected_minimum_errors,
    ) == ([], True, True), (scans.scanned, scans.errors)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
