"""Tests for projecting failure details from scenario step results."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.planner.types import ScenarioArtifactKind
from sqlbuild.executor.scenario._helpers.lifecycle.failures import first_failure_details
from sqlbuild.executor.scenario.models import (
    ScenarioFailureDetails,
    ScenarioFixtureExecutionResult,
)
from sqlbuild.executor.scheduling.types import ExecutionStatus
from tests.unit.src.sqlbuild.executor.scenario._helpers._test_types import (
    FirstFailureDetailsTestCase,
)

_FAILED: ExecutionStatus = ExecutionStatus.FAILED
_SUCCESS: ExecutionStatus = ExecutionStatus.SUCCESS


@pytest.mark.parametrize(
    "test_case",
    (
        FirstFailureDetailsTestCase(
            description="no failed step yields no message and the fallback code",
            step_outcomes=((_SUCCESS, "S100", "help", "ignored"),),
            fallback_code="S999",
            expected_error_code="S999",
            expected_error_help=None,
            expected_error_message=None,
        ),
        FirstFailureDetailsTestCase(
            description="first failed step supplies every detail",
            step_outcomes=(
                (_SUCCESS, "S100", "success help", "success message"),
                (_FAILED, "S200", "orders help", "orders failed"),
                (_FAILED, "S300", "customers help", "customers failed"),
            ),
            fallback_code=None,
            expected_error_code="S200",
            expected_error_help="orders help",
            expected_error_message="orders failed",
        ),
        FirstFailureDetailsTestCase(
            description="missing message uses the fallback message",
            step_outcomes=((_FAILED, "S200", None, None),),
            fallback_code=None,
            expected_error_code="S200",
            expected_error_help=None,
            expected_error_message="step failed",
        ),
        FirstFailureDetailsTestCase(
            description="code and help come from the first failed step that has them",
            step_outcomes=(
                (_FAILED, None, None, "orders failed"),
                (_FAILED, "S300", "customers help", "customers failed"),
            ),
            fallback_code="S999",
            expected_error_code="S300",
            expected_error_help="customers help",
            expected_error_message="orders failed",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_step_results_when_projecting_failure_then_returns_expected_details(
    test_case: FirstFailureDetailsTestCase,
) -> None:
    results: tuple[ScenarioFixtureExecutionResult, ...] = tuple(
        ScenarioFixtureExecutionResult(
            scenario_name="orders_refund",
            kind=ScenarioArtifactKind.SOURCE,
            logical_name=f"fixture_{index}",
            target_relation=f"scenario_schema.fixture_{index}",
            status=status,
            error_code=code,
            error_help=help_text,
            error_message=message,
        )
        for index, (status, code, help_text, message) in enumerate(test_case.step_outcomes)
    )

    details: ScenarioFailureDetails = first_failure_details(
        results=results, fallback_message="step failed", fallback_code=test_case.fallback_code
    )

    assert details == ScenarioFailureDetails(
        error_code=test_case.expected_error_code,
        error_help=test_case.expected_error_help,
        error_message=test_case.expected_error_message,
    )
