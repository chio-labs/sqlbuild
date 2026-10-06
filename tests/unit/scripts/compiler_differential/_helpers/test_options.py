"""Per-engine environment options parse into exact overrides."""

from __future__ import annotations

import argparse

import pytest

from scripts.compiler_differential._helpers.options import (
    parse_engine_environment,
    parse_expected_outcome,
)
from scripts.compiler_differential.exceptions import DifferentialUsageError
from scripts.compiler_differential.models import ExpectedOutcome
from tests.unit.scripts.compiler_differential._helpers._test_types import (
    EngineEnvironmentErrorTestCase,
    EngineEnvironmentTestCase,
    ExpectedOutcomeErrorTestCase,
    ExpectedOutcomeTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        EngineEnvironmentTestCase(
            description="grouped_by_engine",
            values=("native:PYTHONPATH=/tmp/hook", "native:ORDERS_REGION=a=b", "python:EMPTY="),
            expected_environment={
                "native": {"PYTHONPATH": "/tmp/hook", "ORDERS_REGION": "a=b"},
                "python": {"EMPTY": ""},
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_engine_assignments_when_parsing_then_values_group_by_engine(
    test_case: EngineEnvironmentTestCase,
) -> None:
    assert parse_engine_environment(list(test_case.values)) == test_case.expected_environment


@pytest.mark.parametrize(
    "test_case",
    [
        EngineEnvironmentErrorTestCase(
            description=value.replace(":", "_").replace("=", "_") or "empty",
            value=value,
            expected_message="ENGINE:NAME=VALUE",
        )
        for value in ("native", "native:NAME", ":NAME=1", "native:=1")
    ],
    ids=lambda case: case.description,
)
def test_given_malformed_assignment_when_parsing_then_usage_error_is_raised(
    test_case: EngineEnvironmentErrorTestCase,
) -> None:
    with pytest.raises(DifferentialUsageError, match=test_case.expected_message):
        _ = parse_engine_environment([test_case.value])


@pytest.mark.parametrize(
    "test_case",
    [
        ExpectedOutcomeTestCase(
            description="success", value="success", expected_outcome=ExpectedOutcome()
        ),
        ExpectedOutcomeTestCase(
            description="failure_code",
            value="failure:P001",
            expected_outcome=ExpectedOutcome(error_code="P001"),
        ),
        ExpectedOutcomeTestCase(
            description="rule_code",
            value="failure:SQBRSQL005",
            expected_outcome=ExpectedOutcome(error_code="SQBRSQL005"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_expect_value_when_parsing_then_outcome_matches(
    test_case: ExpectedOutcomeTestCase,
) -> None:
    assert parse_expected_outcome(test_case.value) == test_case.expected_outcome


@pytest.mark.parametrize(
    "test_case",
    [
        ExpectedOutcomeErrorTestCase(
            description=value.replace(":", "_") or "empty",
            value=value,
            expected_message="success or failure:<CODE>",
        )
        for value in ("", "failure", "failure:", "failure:p001", "P001", "ok")
    ],
    ids=lambda case: case.description,
)
def test_given_malformed_expect_value_when_parsing_then_argument_error_is_raised(
    test_case: ExpectedOutcomeErrorTestCase,
) -> None:
    with pytest.raises(argparse.ArgumentTypeError, match=test_case.expected_message):
        _ = parse_expected_outcome(test_case.value)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
