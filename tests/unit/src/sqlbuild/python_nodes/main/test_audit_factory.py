"""Tests for the public audit-factory authoring API."""

from __future__ import annotations

import json
from datetime import date
from typing import cast

import pytest

from sqlbuild.audits import (
    AuditCase,
    MeasurementThresholdBound,
    ThresholdOperator,
    above,
    audit_factory,
    below,
    get_audit_factory_definition,
    outside,
)
from sqlbuild.errors.contracts.exceptions import SharedInputError
from sqlbuild.python_nodes.models import AuditFactoryDefinition
from tests.unit.src.sqlbuild.python_nodes.main._test_types import (
    AuditCaseMetaTestCase,
    AuditDecoratorTestCase,
    AuditThresholdHelperTestCase,
    InvalidAuditCaseMetaTestCase,
    InvalidAuditCaseNameTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [AuditDecoratorTestCase("both decorator forms", "bare_factory", "called_factory")],
    ids=lambda case: case.description,
)
def test_given_bare_and_called_decorators_when_applied_then_metadata_is_readable(
    test_case: AuditDecoratorTestCase,
) -> None:
    @audit_factory
    def bare_factory() -> list[AuditCase]:
        return []

    @audit_factory()
    def called_factory() -> list[AuditCase]:
        return []

    bare_definition: AuditFactoryDefinition | None = get_audit_factory_definition(bare_factory)
    called_definition: AuditFactoryDefinition | None = get_audit_factory_definition(called_factory)
    assert bare_definition is not None
    assert called_definition is not None
    assert bare_definition.name == test_case.expected_bare_name
    assert called_definition.name == test_case.expected_called_name


@pytest.mark.parametrize(
    "test_case",
    [AuditThresholdHelperTestCase("directional bounds", 1, 3, ThresholdOperator.OUTSIDE)],
    ids=lambda case: case.description,
)
def test_given_threshold_helpers_when_called_then_directional_bounds_are_returned(
    test_case: AuditThresholdHelperTestCase,
) -> None:
    assert below(10).operator is ThresholdOperator.BELOW
    assert above(20).operator is ThresholdOperator.ABOVE
    outside_bound: MeasurementThresholdBound = outside(lower=test_case.lower, upper=test_case.upper)
    assert outside_bound.operator is test_case.expected_operator
    assert (outside_bound.lower, outside_bound.upper) == (test_case.lower, test_case.upper)


@pytest.mark.parametrize(
    "test_case",
    [
        InvalidAuditCaseNameTestCase("empty", "", "lowercase identifier"),
        InvalidAuditCaseNameTestCase("uppercase", "HasCaps", "lowercase identifier"),
        InvalidAuditCaseNameTestCase("dash", "has-dash", "lowercase identifier"),
        InvalidAuditCaseNameTestCase(
            "leading number", "1starts_with_number", "lowercase identifier"
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_name_when_constructing_audit_case_then_input_error_is_raised(
    test_case: InvalidAuditCaseNameTestCase,
) -> None:
    with pytest.raises(SharedInputError, match=test_case.expected_error_fragment):
        AuditCase(name=test_case.name, definition="expression_is_true")


@pytest.mark.parametrize(
    "test_case",
    [
        AuditCaseMetaTestCase("absent", None, "null"),
        AuditCaseMetaTestCase("empty", {}, "{}"),
        AuditCaseMetaTestCase(
            "nested JSON values",
            {
                "region": "emea",
                "priority": 2,
                "weight": 0.5,
                "active": True,
                "owner": None,
                "channels": ["web", ("store", 3)],
                "exclusion": {"reason": "before launch", "since": "2020-01-01"},
            },
            '{"region": "emea", "priority": 2, "weight": 0.5, "active": true, "owner": null, '
            '"channels": ["web", ["store", 3]], '
            '"exclusion": {"reason": "before launch", "since": "2020-01-01"}}',
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_json_meta_when_constructing_audit_case_then_meta_is_kept_unchanged(
    test_case: AuditCaseMetaTestCase,
) -> None:
    case: AuditCase = AuditCase(
        name="valid_orders", definition="expression_is_true", meta=test_case.meta
    )

    assert case.meta is test_case.meta
    assert json.dumps(case.meta) == test_case.expected_meta_json


@pytest.mark.parametrize(
    "test_case",
    [
        InvalidAuditCaseMetaTestCase(
            "not a mapping", ["emea"], "meta must be a mapping of JSON values"
        ),
        InvalidAuditCaseMetaTestCase(
            "non-string key", {1: "emea"}, "key 1 in meta is not a string"
        ),
        InvalidAuditCaseMetaTestCase(
            "nested date", {"window": {"since": date(2020, 1, 1)}}, r"meta\['window'\]\['since'\]"
        ),
        InvalidAuditCaseMetaTestCase(
            "non-finite number", {"weight": float("nan")}, "is not JSON-serialisable: nan"
        ),
        InvalidAuditCaseMetaTestCase(
            "set in list", {"regions": [{"emea"}]}, r"meta\['regions'\]\[0\]"
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_non_json_meta_when_constructing_audit_case_then_input_error_names_the_value(
    test_case: InvalidAuditCaseMetaTestCase,
) -> None:
    with pytest.raises(SharedInputError, match=test_case.expected_error_fragment) as error:
        AuditCase(
            name="valid_orders",
            definition="expression_is_true",
            meta=cast("dict[str, object]", test_case.meta),
        )

    assert "AuditCase 'valid_orders'" in str(error.value)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
