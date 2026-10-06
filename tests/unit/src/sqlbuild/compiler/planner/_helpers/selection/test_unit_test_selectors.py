"""Splitting unit-test selectors from resource selectors, and rejecting them elsewhere."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.planner._helpers.selection.unit_test_selectors import (
    split_unit_test_selectors,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import (
    SqlTestSelection,
    UnitTestSelectorNames,
    UnitTestSelectorSplit,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.selection._test_types import (
    UnitTestSelectorErrorTestCase,
    UnitTestSelectorSplitTestCase,
)

_NAMES: UnitTestSelectorNames = UnitTestSelectorNames(
    tests=frozenset({"order_status", "order_totals_check", "customer_status"}),
    resources=frozenset({"orders", "order_totals", "customers", "raw_orders"}),
)


@pytest.mark.parametrize(
    "test_case",
    [
        UnitTestSelectorSplitTestCase(
            description="a bare test name selects only that test and no models",
            select=("order_status",),
            exclude=(),
            expected_select=(),
            expected_exclude=(),
            expected_selection=SqlTestSelection(
                names=frozenset({"order_status"}), models_selected=False
            ),
        ),
        UnitTestSelectorSplitTestCase(
            description="test: selectors union with model selectors",
            select=("test:customer_status orders+", "tag:daily"),
            exclude=(),
            expected_select=("orders+", "tag:daily"),
            expected_exclude=(),
            expected_selection=SqlTestSelection(names=frozenset({"customer_status"})),
        ),
        UnitTestSelectorSplitTestCase(
            description="test: patterns match unit tests with fnmatch",
            select=("test:order_*",),
            exclude=(),
            expected_select=(),
            expected_exclude=(),
            expected_selection=SqlTestSelection(
                names=frozenset({"order_status", "order_totals_check"}), models_selected=False
            ),
        ),
        UnitTestSelectorSplitTestCase(
            description="a bare pattern that matches resources keeps its resource meaning",
            select=("order*",),
            exclude=("test:order_totals_check",),
            expected_select=("order*",),
            expected_exclude=(),
            expected_selection=SqlTestSelection(excluded_names=frozenset({"order_totals_check"})),
        ),
        UnitTestSelectorSplitTestCase(
            description="empty and blank select values are kept and select nothing",
            select=("", "  "),
            exclude=(),
            expected_select=("", "  "),
            expected_exclude=(),
            expected_selection=SqlTestSelection(),
        ),
        UnitTestSelectorSplitTestCase(
            description="a test-only selector beside an empty value still selects no models",
            select=("", "order_status"),
            exclude=(),
            expected_select=("",),
            expected_exclude=(),
            expected_selection=SqlTestSelection(names=frozenset({"order_status"})),
        ),
        UnitTestSelectorSplitTestCase(
            description="selectors without unit tests pass through unchanged",
            select=("orders", "customers,tag:daily", "models/marts"),
            exclude=("raw_orders",),
            expected_select=("orders", "customers,tag:daily", "models/marts"),
            expected_exclude=("raw_orders",),
            expected_selection=SqlTestSelection(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_selectors_when_splitting_unit_tests_then_tests_and_resources_separate(
    test_case: UnitTestSelectorSplitTestCase,
) -> None:
    split: UnitTestSelectorSplit = split_unit_test_selectors(
        select=test_case.select,
        exclude=test_case.exclude,
        names=_NAMES,
        accepts_unit_tests=True,
    )

    assert split.select == test_case.expected_select
    assert split.exclude == test_case.expected_exclude
    assert split.sql_test_selection == test_case.expected_selection


@pytest.mark.parametrize(
    "test_case",
    [
        UnitTestSelectorErrorTestCase(
            description="a command that runs no unit tests rejects a bare test name",
            select=("order_status",),
            accepts_unit_tests=False,
            expected_code="S013",
            expected_message=(
                "selector 'order_status' selects a unit test; only `sqb test` and `sqb build` "
                "accept unit-test selectors"
            ),
            expected_help=None,
        ),
        UnitTestSelectorErrorTestCase(
            description="a command that runs no unit tests rejects test: selectors",
            select=("orders test:customer_status",),
            accepts_unit_tests=False,
            expected_code="S013",
            expected_message=(
                "selector 'test:customer_status' selects a unit test; only `sqb test` and "
                "`sqb build` accept unit-test selectors"
            ),
            expected_help=None,
        ),
        UnitTestSelectorErrorTestCase(
            description="an unknown test: name suggests the nearest unit tests",
            select=("test:order_stats",),
            accepts_unit_tests=True,
            expected_code="S007",
            expected_message="unknown unit test name 'order_stats'",
            expected_help="did you mean 'order_status'?",
        ),
        UnitTestSelectorErrorTestCase(
            description="an unknown bare name suggests unit tests and resources",
            select=("customer_stat",),
            accepts_unit_tests=True,
            expected_code="S007",
            expected_message="unknown selector name 'customer_stat'",
            expected_help="did you mean 'customer_status', 'customers'?",
        ),
        UnitTestSelectorErrorTestCase(
            description="graph expansion of a unit test is refused",
            select=("+order_status",),
            accepts_unit_tests=True,
            expected_code="S013",
            expected_message=(
                "selector '+order_status' expands a unit test with '+'; unit tests have no "
                "lineage, so select them by name without '+'"
            ),
            expected_help=None,
        ),
        UnitTestSelectorErrorTestCase(
            description="intersecting a unit test is refused",
            select=("order_status,tag:daily",),
            accepts_unit_tests=True,
            expected_code="S013",
            expected_message=(
                "selector 'order_status,tag:daily' intersects a unit test with ','; unit tests "
                "can only be selected whole, by name"
            ),
            expected_help=None,
        ),
        UnitTestSelectorErrorTestCase(
            description="a stray trailing comma after a unit test reports the empty selector",
            select=("test:order_status,",),
            accepts_unit_tests=True,
            expected_code="S001",
            expected_message="empty selector",
            expected_help=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_unit_test_selectors_when_splitting_then_it_raises_clear_errors(
    test_case: UnitTestSelectorErrorTestCase,
) -> None:
    with pytest.raises(PlannerInputError) as raised:
        split_unit_test_selectors(
            select=test_case.select,
            exclude=(),
            names=_NAMES,
            accepts_unit_tests=test_case.accepts_unit_tests,
        )

    assert raised.value.code == test_case.expected_code
    assert raised.value.message == test_case.expected_message
    assert raised.value.help == test_case.expected_help


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
