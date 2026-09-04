"""Test case types for expectation detail formatting."""

from dataclasses import dataclass

from sqlbuild.executor.testing.models import StepResult


@dataclass(frozen=True)
class ExpectationDetailTestCase:
    """One expected-output detail formatting case."""

    description: str
    step_result: StepResult
    expected_fragments: tuple[str, ...]
