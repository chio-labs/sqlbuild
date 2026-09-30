"""Tests for authored-text edit application and identifier matching."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.refactoring._helpers.text_edits import apply_text_edits, identifier_sites
from sqlbuild.compiler.refactoring.exceptions import RefactorEditError
from tests.unit.src.sqlbuild.compiler.refactoring._helpers._test_types import (
    ApplyEditsErrorTestCase,
    ApplyEditsTestCase,
    IdentifierSitesTestCase,
)
from tests.unit.src.sqlbuild.compiler.refactoring._helpers.helpers import span_edits


@pytest.mark.parametrize(
    "test_case",
    [
        ApplyEditsTestCase(
            description="identical duplicate edits apply once",
            text="SELECT amount FROM orders",
            spans=((7, 13, "revenue"), (7, 13, "revenue")),
            expected_text="SELECT revenue FROM orders",
        ),
        ApplyEditsTestCase(
            description="insertions and replacements apply back to front",
            text="SELECT amount FROM orders",
            spans=((7, 13, "revenue"), (13, 13, " AS amount")),
            expected_text="SELECT revenue AS amount FROM orders",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_edits_when_applying_then_text_is_rewritten(test_case: ApplyEditsTestCase) -> None:
    assert (
        apply_text_edits(
            text=test_case.text, edits=span_edits(text=test_case.text, spans=test_case.spans)
        )
        == test_case.expected_text
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ApplyEditsErrorTestCase(
            description="overlapping replacements",
            text="SELECT amount FROM orders",
            spans=((7, 13, "revenue"), (10, 18, "x")),
            expected_error=RefactorEditError,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_overlapping_edits_when_applying_then_refuses(
    test_case: ApplyEditsErrorTestCase,
) -> None:
    with pytest.raises(test_case.expected_error):
        _ = apply_text_edits(
            text=test_case.text, edits=span_edits(text=test_case.text, spans=test_case.spans)
        )


@pytest.mark.parametrize(
    "test_case",
    [
        IdentifierSitesTestCase(
            description="matches whole unquoted identifiers only",
            text="__ref__orders AS (SELECT 1), __ref__orders_daily AS (SELECT 2)",
            expected_offsets=(0,),
        ),
        IdentifierSitesTestCase(
            description="skips comments and string literals",
            text="-- __ref__orders\nSELECT '__ref__orders', __ref__orders",
            expected_offsets=(41,),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_text_when_finding_identifiers_then_code_sites_match(
    test_case: IdentifierSitesTestCase,
) -> None:
    sites: tuple[tuple[int, int, str], ...] = identifier_sites(
        text=test_case.text, names=frozenset({"__ref__orders"})
    )

    assert tuple(start for start, _, _ in sites) == test_case.expected_offsets


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
