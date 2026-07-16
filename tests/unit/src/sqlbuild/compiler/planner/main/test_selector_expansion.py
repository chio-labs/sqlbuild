from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.main.selection.selector_expansion import split_selector_expansion
from sqlbuild.compiler.planner.models import SelectorExpansion
from tests.unit.src.sqlbuild.compiler.planner.main._test_types import (
    SelectorExpansionErrorTestCase,
    SelectorExpansionTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SelectorExpansionTestCase(
            description="splits bare selector",
            raw="orders",
            expected_core="orders",
            expected_upstream=False,
            expected_downstream=False,
        ),
        SelectorExpansionTestCase(
            description="splits bidirectional selector",
            raw="+orders+",
            expected_core="orders",
            expected_upstream=True,
            expected_downstream=True,
        ),
        SelectorExpansionTestCase(
            description="preserves dbt-native comma selector core",
            raw="state:modified,tag:daily+",
            expected_core="state:modified,tag:daily",
            expected_upstream=False,
            expected_downstream=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_selector_when_splitting_expansion_then_returns_expected_parts(
    test_case: SelectorExpansionTestCase,
) -> None:
    result: SelectorExpansion = split_selector_expansion(test_case.raw)

    assert result.core == test_case.expected_core
    assert result.upstream == test_case.expected_upstream
    assert result.downstream == test_case.expected_downstream


@pytest.mark.parametrize(
    "test_case",
    [
        SelectorExpansionErrorTestCase(
            description="rejects empty selector",
            raw="",
            expected_error_type=ValueError,
        ),
        SelectorExpansionErrorTestCase(
            description="rejects whitespace selector",
            raw="   ",
            expected_error_type=ValueError,
        ),
        SelectorExpansionErrorTestCase(
            description="rejects marker-only selector",
            raw="+",
            expected_error_type=ValueError,
        ),
        SelectorExpansionErrorTestCase(
            description="rejects unsupported marker position",
            raw="orders+daily",
            expected_error_type=ValueError,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_selector_when_splitting_expansion_then_raises(
    test_case: SelectorExpansionErrorTestCase,
) -> None:
    with pytest.raises(test_case.expected_error_type):
        split_selector_expansion(test_case.raw)
